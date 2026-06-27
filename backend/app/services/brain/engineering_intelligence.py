"""EngineeringIntelligenceService (Phase 12.2 — Engineering Intelligence).

Read-only engineering reasoning over the persistent knowledge graph: module /
service / endpoint maps, dependency and impact analysis, and architecture review.

It never executes code or writes to GitHub. It is the layer the later Debug
Intelligence phase (12.3) will use to map a failure to affected files; here it
only surfaces structure and impact for humans to act on.
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.brain_knowledge import BrainKnowledgeEdge, BrainKnowledgeNode
from app.services.brain.knowledge_service import KnowledgeGraphService

# Node types that represent code/structure (vs. transient signals like risk/audit).
CODE_NODE_TYPES = ("module", "service", "endpoint", "migration", "test", "model", "repository", "integration", "feature")
# Node types that represent concrete artifacts a change would touch.
ARTIFACT_TYPES = ("module", "service", "endpoint", "migration", "test", "model")
# Relationship types that express a dependency direction (from depends on to).
DEPENDENCY_RELS = ("depends_on", "uses", "belongs_to", "implements", "validates", "exposes")
HOTSPOT_MIN_DEPENDENTS = 3


def _node_brief(node: BrainKnowledgeNode) -> dict:
    return {
        "id": str(node.id),
        "node_type": node.node_type,
        "title": node.title,
        "confidence": node.confidence_score,
    }


class EngineeringIntelligenceService:
    def __init__(self, db: Session, *, graph: KnowledgeGraphService | None = None) -> None:
        self.db = db
        self.graph = graph or KnowledgeGraphService(db)

    # -- internal graph load ---------------------------------------------------

    def _load(self, organization_id: uuid.UUID):
        nodes = {
            n.id: n
            for n in self.db.scalars(
                select(BrainKnowledgeNode).where(BrainKnowledgeNode.organization_id == organization_id)
            )
        }
        edges = list(
            self.db.scalars(
                select(BrainKnowledgeEdge).where(BrainKnowledgeEdge.organization_id == organization_id)
            )
        )
        return nodes, edges

    # -- overview --------------------------------------------------------------

    def overview(self, organization_id: uuid.UUID) -> dict:
        nodes, edges = self._load(organization_id)
        node_counts: dict[str, int] = defaultdict(int)
        for n in nodes.values():
            if n.node_type in CODE_NODE_TYPES:
                node_counts[n.node_type] += 1
        edge_counts: dict[str, int] = defaultdict(int)
        in_degree: dict[uuid.UUID, int] = defaultdict(int)
        connected: set[uuid.UUID] = set()
        for e in edges:
            edge_counts[e.relationship_type] += 1
            connected.add(e.from_node_id)
            connected.add(e.to_node_id)
            if e.relationship_type in DEPENDENCY_RELS:
                in_degree[e.to_node_id] += 1

        top = sorted(in_degree.items(), key=lambda kv: kv[1], reverse=True)[:5]
        top_dependencies = [
            {**_node_brief(nodes[nid]), "dependents": deg} for nid, deg in top if nid in nodes
        ]
        orphans = sum(
            1 for n in nodes.values() if n.node_type in CODE_NODE_TYPES and n.id not in connected
        )
        total_code = sum(node_counts.values())
        return {
            "node_counts": dict(node_counts),
            "edge_counts": dict(edge_counts),
            "top_dependencies": top_dependencies,
            "orphans": orphans,
            "total_components": total_code,
            "summary": (
                f"{total_code} code component(s) across {len(node_counts)} type(s); "
                f"{len(edges)} relationship(s); {orphans} orphan(s). "
                + (f"Most depended-on: {top_dependencies[0]['title']}." if top_dependencies else "No dependencies recorded.")
            ),
        }

    # -- impact analysis -------------------------------------------------------

    def impact(self, organization_id: uuid.UUID, query: str, *, limit: int = 8) -> dict:
        nodes, edges = self._load(organization_id)
        adjacency: dict[uuid.UUID, list[BrainKnowledgeEdge]] = defaultdict(list)
        for e in edges:
            adjacency[e.from_node_id].append(e)
            adjacency[e.to_node_id].append(e)

        matches = self.graph.search(organization_id, query, limit=limit)
        impacted: dict[uuid.UUID, dict] = {}
        for m in matches:
            for e in adjacency.get(m.id, []):
                other_id = e.to_node_id if e.from_node_id == m.id else e.from_node_id
                other = nodes.get(other_id)
                if other is None or other.id == m.id:
                    continue
                impacted.setdefault(
                    other.id,
                    {**_node_brief(other), "via": e.relationship_type, "from": m.title},
                )

        affected_by_type: dict[str, list[dict]] = defaultdict(list)
        for entry in impacted.values():
            if entry["node_type"] in ARTIFACT_TYPES:
                affected_by_type[entry["node_type"]].append(entry)

        return {
            "query": query,
            "matches": [_node_brief(m) for m in matches],
            "impacted": list(impacted.values()),
            "affected_by_type": {k: v for k, v in affected_by_type.items()},
            "summary": (
                f"{len(matches)} matching component(s); {len(impacted)} connected component(s) "
                f"would likely be affected by a change."
                if matches
                else "No matching components in the graph; run knowledge ingestion first."
            ),
        }

    # -- dependency mapping ----------------------------------------------------

    def dependencies(self, organization_id: uuid.UUID, node_id: uuid.UUID) -> dict:
        node = self.graph.get_node(node_id, organization_id)
        nodes, edges = self._load(organization_id)
        dependencies, dependents = [], []
        for e in edges:
            if e.relationship_type not in DEPENDENCY_RELS:
                continue
            if e.from_node_id == node_id and e.to_node_id in nodes:
                dependencies.append({**_node_brief(nodes[e.to_node_id]), "relationship": e.relationship_type})
            elif e.to_node_id == node_id and e.from_node_id in nodes:
                dependents.append({**_node_brief(nodes[e.from_node_id]), "relationship": e.relationship_type})
        return {
            "node": _node_brief(node),
            "dependencies": dependencies,
            "dependents": dependents,
            "summary": (
                f"{node.title} depends on {len(dependencies)} component(s) and is depended on by "
                f"{len(dependents)} component(s)."
            ),
        }

    # -- architecture review ---------------------------------------------------

    def architecture_review(self, organization_id: uuid.UUID) -> dict:
        nodes, edges = self._load(organization_id)
        in_degree: dict[uuid.UUID, int] = defaultdict(int)
        connected: set[uuid.UUID] = set()
        integration_coupling: list[dict] = []
        for e in edges:
            connected.add(e.from_node_id)
            connected.add(e.to_node_id)
            if e.relationship_type in DEPENDENCY_RELS:
                in_degree[e.to_node_id] += 1
            if e.relationship_type in ("depends_on", "uses"):
                frm, to = nodes.get(e.from_node_id), nodes.get(e.to_node_id)
                if frm and to and to.node_type == "integration":
                    integration_coupling.append({"from": frm.title, "integration": to.title})

        flags: list[dict] = []
        # Hotspots: high fan-in components — change with care.
        for nid, deg in in_degree.items():
            if deg >= HOTSPOT_MIN_DEPENDENTS and nid in nodes:
                n = nodes[nid]
                flags.append({
                    "title": f"High fan-in: {n.title}",
                    "severity": "medium",
                    "detail": f"{deg} component(s) depend on this; changes carry broad impact.",
                    "evidence": [{"source": "graph", "detail": f"in-degree={deg}", "reference": str(n.id)}],
                })
        # Orphans: code components with no relationships.
        orphans = [
            n for n in nodes.values() if n.node_type in CODE_NODE_TYPES and n.id not in connected
        ]
        if orphans:
            flags.append({
                "title": f"{len(orphans)} orphan component(s)",
                "severity": "low",
                "detail": "Components with no recorded relationships; may be unused or under-documented.",
                "evidence": [{"source": "graph", "detail": o.title, "reference": str(o.id)} for o in orphans[:5]],
            })
        # Stale knowledge.
        stale = [n for n in nodes.values() if n.node_type in CODE_NODE_TYPES and self.graph.is_stale(n)]
        if stale:
            flags.append({
                "title": f"{len(stale)} stale knowledge node(s)",
                "severity": "low",
                "detail": "Knowledge not refreshed recently; re-ingest to keep the graph current.",
                "evidence": [{"source": "graph", "detail": s.title, "reference": str(s.id)} for s in stale[:5]],
            })
        if integration_coupling:
            flags.append({
                "title": f"{len(integration_coupling)} integration coupling(s)",
                "severity": "info",
                "detail": "Services that depend on external integrations.",
                "evidence": [
                    {"source": "graph", "detail": f"{c['from']} -> {c['integration']}", "reference": None}
                    for c in integration_coupling[:5]
                ],
            })

        flags.sort(key=lambda f: {"high": 3, "medium": 2, "low": 1, "info": 0}.get(f["severity"], 0), reverse=True)
        return {
            "flags": flags,
            "summary": (f"{len(flags)} architecture observation(s)." if flags else "No architecture concerns detected."),
        }

    def get_node(self, node_id: uuid.UUID, organization_id: uuid.UUID) -> BrainKnowledgeNode:
        node = self.db.scalar(
            select(BrainKnowledgeNode).where(
                BrainKnowledgeNode.id == node_id, BrainKnowledgeNode.organization_id == organization_id
            )
        )
        if not node:
            raise NotFoundError("Component not found")
        return node
