from __future__ import annotations

from app.services.brain.engineering_intelligence import EngineeringIntelligenceService
from app.services.brain.knowledge_service import KnowledgeGraphService

BASE = "/api/v1/brain/engineering"


def _graph(api_context) -> KnowledgeGraphService:
    return KnowledgeGraphService(api_context.db)


def _seed(api_context):
    """A tiny graph: two services depend on a shared integration; one orphan."""
    g = _graph(api_context)
    org = api_context.organization.id
    integ = g.upsert_node(organization_id=org, node_type="integration", title="GitHub integration",
                          source_type="integration", source_id="github")
    svc_a = g.upsert_node(organization_id=org, node_type="service", title="app.services.workspace",
                          source_type="service", source_id="app.services.workspace", summary="workspace launch")
    svc_b = g.upsert_node(organization_id=org, node_type="service", title="app.services.agent",
                          source_type="service", source_id="app.services.agent")
    svc_c = g.upsert_node(organization_id=org, node_type="service", title="app.services.execution",
                          source_type="service", source_id="app.services.execution")
    test = g.upsert_node(organization_id=org, node_type="test", title="test_workspace_launcher",
                         source_type="test", source_id="test_workspace_launcher")
    g.upsert_node(organization_id=org, node_type="module", title="orphan.module",
                  source_type="module", source_id="orphan")  # no edges -> orphan
    g.upsert_edge(organization_id=org, from_node_id=svc_a.id, to_node_id=integ.id, relationship_type="depends_on")
    g.upsert_edge(organization_id=org, from_node_id=svc_b.id, to_node_id=integ.id, relationship_type="depends_on")
    g.upsert_edge(organization_id=org, from_node_id=svc_c.id, to_node_id=integ.id, relationship_type="uses")
    g.upsert_edge(organization_id=org, from_node_id=test.id, to_node_id=svc_a.id, relationship_type="validates")
    api_context.db.commit()
    return {"integ": integ, "svc_a": svc_a, "test": test}


def test_overview_counts_and_top_dependencies(api_context) -> None:
    _seed(api_context)
    ov = EngineeringIntelligenceService(api_context.db).overview(api_context.organization.id)
    assert ov["node_counts"].get("service") == 3
    assert ov["total_components"] >= 5
    # GitHub integration is depended on by 3 services -> top dependency.
    assert ov["top_dependencies"]
    assert ov["top_dependencies"][0]["title"] == "GitHub integration"
    assert ov["top_dependencies"][0]["dependents"] == 3
    assert ov["orphans"] >= 1


def test_impact_finds_affected_components(api_context) -> None:
    seeded = _seed(api_context)
    impact = EngineeringIntelligenceService(api_context.db).impact(api_context.organization.id, "workspace")
    assert any(m["title"] == "app.services.workspace" for m in impact["matches"])
    # The validating test and the integration are connected -> impacted.
    impacted_titles = {i["title"] for i in impact["impacted"]}
    assert "test_workspace_launcher" in impacted_titles or "GitHub integration" in impacted_titles
    assert "test" in impact["affected_by_type"] or impact["impacted"]


def test_dependencies_dependents_and_dependencies(api_context) -> None:
    seeded = _seed(api_context)
    svc = EngineeringIntelligenceService(api_context.db)
    # The integration is depended on by services (dependents) and depends on nothing.
    dep = svc.dependencies(api_context.organization.id, seeded["integ"].id)
    assert dep["dependencies"] == []
    assert len(dep["dependents"]) == 3
    # A service depends on the integration (dependency) and is validated by a test (dependent).
    dep_a = svc.dependencies(api_context.organization.id, seeded["svc_a"].id)
    assert any(d["title"] == "GitHub integration" for d in dep_a["dependencies"])
    assert any(d["title"] == "test_workspace_launcher" for d in dep_a["dependents"])


def test_architecture_review_flags(api_context) -> None:
    _seed(api_context)
    review = EngineeringIntelligenceService(api_context.db).architecture_review(api_context.organization.id)
    titles = " ".join(f["title"] for f in review["flags"])
    assert "High fan-in" in titles  # integration has 3 dependents
    assert "orphan" in titles.lower()
    assert any(f["severity"] == "info" for f in review["flags"])  # integration coupling


def test_org_isolation(api_context) -> None:
    _seed(api_context)
    other = EngineeringIntelligenceService(api_context.db).overview(api_context.other_organization.id)
    assert other["total_components"] == 0


def test_engineering_brain_uses_intelligence(api_context) -> None:
    _seed(api_context)
    from app.services.brain.super_brain import SuperBrainOrchestrator

    run = SuperBrainOrchestrator(api_context.db).ask(
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        question="which services depend on github and what is impacted by workspace changes?",
    )
    assert "engineering" in run.brains_consulted
    # Evidence should include a dependency or impact entry from the graph.
    sources = {e.get("source") for e in run.evidence}
    assert sources & {"dependency", "impact", "architecture"}


# -- API ----------------------------------------------------------------------


def test_api_engineering_endpoints(api_context) -> None:
    seeded = _seed(api_context)
    ov = api_context.client.get(f"{BASE}/overview")
    assert ov.status_code == 200 and ov.json()["total_components"] >= 5

    impact = api_context.client.get(f"{BASE}/impact?query=workspace")
    assert impact.status_code == 200 and "impacted" in impact.json()

    deps = api_context.client.get(f"{BASE}/dependencies?node_id={seeded['integ'].id}")
    assert deps.status_code == 200 and len(deps.json()["dependents"]) == 3

    arch = api_context.client.get(f"{BASE}/architecture")
    assert arch.status_code == 200 and "flags" in arch.json()
