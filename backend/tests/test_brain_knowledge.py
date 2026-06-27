from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update

from app.core.errors import NotFoundError
from app.models.brain import BrainDecision
from app.models.brain_knowledge import BrainKnowledgeNode
from app.models.workspace_instance import WorkspaceInstance
from app.services.brain.knowledge_ingestion import KnowledgeIngestionService
from app.services.brain.knowledge_service import KnowledgeGraphService
from app.services.brain.super_brain import BrainContextBuilder

BASE = "/api/v1/brain/knowledge"


def _graph(api_context) -> KnowledgeGraphService:
    return KnowledgeGraphService(api_context.db)


# -- node / edge CRUD ---------------------------------------------------------


def test_node_upsert_is_idempotent(api_context) -> None:
    g = _graph(api_context)
    a = g.upsert_node(organization_id=api_context.organization.id, node_type="service", title="svc",
                      source_type="service", source_id="app.services.x", summary="v1")
    api_context.db.commit()
    b = g.upsert_node(organization_id=api_context.organization.id, node_type="service", title="svc2",
                      source_type="service", source_id="app.services.x", summary="v2")
    api_context.db.commit()
    assert a.id == b.id
    assert b.summary == "v2"


def test_edge_upsert_is_idempotent(api_context) -> None:
    g = _graph(api_context)
    n1 = g.upsert_node(organization_id=api_context.organization.id, node_type="module", title="m1",
                       source_type="module", source_id="m1")
    n2 = g.upsert_node(organization_id=api_context.organization.id, node_type="module", title="m2",
                       source_type="module", source_id="m2")
    api_context.db.commit()
    e1 = g.upsert_edge(organization_id=api_context.organization.id, from_node_id=n1.id, to_node_id=n2.id,
                       relationship_type="depends_on")
    e2 = g.upsert_edge(organization_id=api_context.organization.id, from_node_id=n1.id, to_node_id=n2.id,
                       relationship_type="depends_on", confidence_score=0.9)
    api_context.db.commit()
    assert e1.id == e2.id
    assert e2.confidence_score == 0.9


def test_secret_redaction_on_upsert(api_context) -> None:
    g = _graph(api_context)
    n = g.upsert_node(organization_id=api_context.organization.id, node_type="decision", title="t",
                      source_type="decision", source_id="d1",
                      summary="token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345")
    api_context.db.commit()
    assert "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345" not in n.summary


# -- ingestion ----------------------------------------------------------------


def test_ingest_from_decisions(api_context) -> None:
    api_context.db.add(
        BrainDecision(organization_id=api_context.organization.id, title="Use Redis lock",
                      decision="Adopt Redis SET NX", confidence=0.8, evidence=[])
    )
    api_context.db.commit()
    KnowledgeIngestionService(api_context.db).ingest(api_context.organization.id)
    nodes = _graph(api_context).by_source(api_context.organization.id, "brain_decision")
    assert any(n.title == "Use Redis lock" for n in nodes)


def test_ingest_from_workspace_links_repository(api_context) -> None:
    ws = WorkspaceInstance(
        organization_id=api_context.organization.id, repository_id=api_context.repository.id, status="running"
    )
    api_context.db.add(ws)
    api_context.db.commit()
    KnowledgeIngestionService(api_context.db).ingest(api_context.organization.id)
    g = _graph(api_context)
    ws_nodes = g.by_source(api_context.organization.id, "workspace_instance", str(ws.id))
    assert ws_nodes
    nb = g.neighborhood(ws_nodes[0].id, api_context.organization.id)
    # The workspace belongs_to its repository.
    assert any(e.relationship_type == "belongs_to" for e in nb["edges"])
    assert any(n.node_type == "repository" for n in nb["neighbors"])


def test_ingest_creates_codebase_nodes(api_context) -> None:
    KnowledgeIngestionService(api_context.db).ingest(api_context.organization.id)
    g = _graph(api_context)
    assert g.list_nodes(api_context.organization.id, node_type="migration")
    assert g.list_nodes(api_context.organization.id, node_type="endpoint")
    assert g.list_nodes(api_context.organization.id, node_type="service")


# -- retrieval ----------------------------------------------------------------


def test_search_and_recall(api_context) -> None:
    g = _graph(api_context)
    g.upsert_node(organization_id=api_context.organization.id, node_type="module", title="Workspace launcher",
                  source_type="module", source_id="wl", summary="handles workspace launch lifecycle")
    api_context.db.commit()
    assert g.search(api_context.organization.id, "workspace")
    assert g.recall(api_context.organization.id, ["workspace", "launch"])


def test_stale_detection(api_context) -> None:
    g = _graph(api_context)
    n = g.upsert_node(organization_id=api_context.organization.id, node_type="module", title="old", source_type="m", source_id="old")
    api_context.db.commit()
    old = datetime.now(timezone.utc) - timedelta(days=90)
    api_context.db.execute(update(BrainKnowledgeNode).where(BrainKnowledgeNode.id == n.id).values(updated_at=old))
    api_context.db.commit()
    api_context.db.refresh(n)
    assert g.is_stale(n)
    assert any(s.id == n.id for s in g.stale_nodes(api_context.organization.id))


# -- context builder uses graph -----------------------------------------------


def test_context_builder_uses_graph(api_context) -> None:
    g = _graph(api_context)
    g.upsert_node(organization_id=api_context.organization.id, node_type="module", title="Workspace launcher",
                  source_type="module", source_id="wl", summary="handles workspace launch")
    api_context.db.commit()
    ctx = BrainContextBuilder().build(api_context.db, api_context.organization.id, "which modules handle workspace launch")
    assert ctx["knowledge"]
    assert any("Workspace" in k["title"] for k in ctx["knowledge"])


# -- org isolation ------------------------------------------------------------


def test_org_isolation(api_context) -> None:
    g = _graph(api_context)
    other = g.upsert_node(organization_id=api_context.other_organization.id, node_type="module", title="secret",
                          source_type="m", source_id="o")
    api_context.db.commit()
    assert all(n.id != other.id for n in g.list_nodes(api_context.organization.id))
    with pytest.raises(NotFoundError):
        g.get_node(other.id, api_context.organization.id)


# -- API ----------------------------------------------------------------------


def test_api_knowledge_flow(api_context) -> None:
    ingest = api_context.client.post(f"{BASE}/ingest")
    assert ingest.status_code == 200
    assert ingest.json()["nodes"] >= 1

    nodes = api_context.client.get(f"{BASE}/nodes")
    assert nodes.status_code == 200 and len(nodes.json()) >= 1
    node_id = nodes.json()[0]["id"]
    assert "metadata" in nodes.json()[0]  # exposed as "metadata"

    detail = api_context.client.get(f"{BASE}/nodes/{node_id}")
    assert detail.status_code == 200

    graph = api_context.client.get(f"{BASE}/graph?node_id={node_id}")
    assert graph.status_code == 200
    assert {"node", "edges", "neighbors"} <= set(graph.json())

    search = api_context.client.get(f"{BASE}/search?query=github")
    assert search.status_code == 200
