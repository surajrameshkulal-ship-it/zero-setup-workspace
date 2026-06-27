"""KnowledgeGraphService — persistent knowledge graph store + retrieval.

Read-only with respect to the product (it never executes code or writes to
GitHub); it only records and connects knowledge CodeDNA already owns. Provides
idempotent upsert of nodes/edges plus retrieval: keyword recall, graph
neighborhood lookup, source-based lookup, confidence filtering, and stale
knowledge detection. Everything is organization-scoped and secret-redacted.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.brain_knowledge import BrainKnowledgeEdge, BrainKnowledgeNode
from app.services.brain.safety_guard import BrainSafetyGuard

STALE_AFTER_DAYS = 30


class KnowledgeGraphService:
    def __init__(self, db: Session, *, guard: BrainSafetyGuard | None = None) -> None:
        self.db = db
        self.guard = guard or BrainSafetyGuard()

    # -- upsert ----------------------------------------------------------------

    def upsert_node(
        self,
        *,
        organization_id: uuid.UUID,
        node_type: str,
        title: str,
        summary: str = "",
        source_type: str | None = None,
        source_id: str | None = None,
        confidence_score: float = 0.5,
        metadata: dict | None = None,
    ) -> BrainKnowledgeNode:
        existing = None
        if source_type is not None and source_id is not None:
            existing = self.db.scalar(
                select(BrainKnowledgeNode).where(
                    BrainKnowledgeNode.organization_id == organization_id,
                    BrainKnowledgeNode.node_type == node_type,
                    BrainKnowledgeNode.source_type == source_type,
                    BrainKnowledgeNode.source_id == source_id,
                )
            )
        title = self.guard.redact(title) or title
        summary = self.guard.redact(summary) or ""
        metadata = self.guard.sanitize(metadata or {})
        if existing is not None:
            existing.title = title
            existing.summary = summary
            existing.confidence_score = confidence_score
            existing.node_metadata = metadata
            self.db.flush()
            return existing
        node = BrainKnowledgeNode(
            organization_id=organization_id,
            node_type=node_type,
            title=title,
            summary=summary,
            source_type=source_type,
            source_id=source_id,
            confidence_score=confidence_score,
            node_metadata=metadata,
        )
        self.db.add(node)
        self.db.flush()
        return node

    def upsert_edge(
        self,
        *,
        organization_id: uuid.UUID,
        from_node_id: uuid.UUID,
        to_node_id: uuid.UUID,
        relationship_type: str,
        confidence_score: float = 0.5,
        evidence: list | None = None,
    ) -> BrainKnowledgeEdge:
        existing = self.db.scalar(
            select(BrainKnowledgeEdge).where(
                BrainKnowledgeEdge.organization_id == organization_id,
                BrainKnowledgeEdge.from_node_id == from_node_id,
                BrainKnowledgeEdge.to_node_id == to_node_id,
                BrainKnowledgeEdge.relationship_type == relationship_type,
            )
        )
        evidence = self.guard.sanitize(evidence or [])
        if existing is not None:
            existing.confidence_score = confidence_score
            existing.evidence = evidence
            self.db.flush()
            return existing
        edge = BrainKnowledgeEdge(
            organization_id=organization_id,
            from_node_id=from_node_id,
            to_node_id=to_node_id,
            relationship_type=relationship_type,
            confidence_score=confidence_score,
            evidence=evidence,
        )
        self.db.add(edge)
        self.db.flush()
        return edge

    # -- retrieval -------------------------------------------------------------

    def get_node(self, node_id: uuid.UUID, organization_id: uuid.UUID) -> BrainKnowledgeNode:
        node = self.db.scalar(
            select(BrainKnowledgeNode).where(
                BrainKnowledgeNode.id == node_id, BrainKnowledgeNode.organization_id == organization_id
            )
        )
        if not node:
            raise NotFoundError("Knowledge node not found")
        return node

    def list_nodes(
        self,
        organization_id: uuid.UUID,
        *,
        node_type: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 200,
    ) -> list[BrainKnowledgeNode]:
        stmt = select(BrainKnowledgeNode).where(
            BrainKnowledgeNode.organization_id == organization_id,
            BrainKnowledgeNode.confidence_score >= min_confidence,
        )
        if node_type:
            stmt = stmt.where(BrainKnowledgeNode.node_type == node_type)
        stmt = stmt.order_by(BrainKnowledgeNode.updated_at.desc()).limit(limit)
        return list(self.db.scalars(stmt))

    def search(
        self,
        organization_id: uuid.UUID,
        query: str,
        *,
        node_type: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 20,
    ) -> list[BrainKnowledgeNode]:
        stmt = select(BrainKnowledgeNode).where(
            BrainKnowledgeNode.organization_id == organization_id,
            BrainKnowledgeNode.confidence_score >= min_confidence,
        )
        if node_type:
            stmt = stmt.where(BrainKnowledgeNode.node_type == node_type)
        if query:
            like = f"%{query.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(BrainKnowledgeNode.title).like(like),
                    func.lower(BrainKnowledgeNode.summary).like(like),
                )
            )
        stmt = stmt.order_by(BrainKnowledgeNode.confidence_score.desc()).limit(limit)
        return list(self.db.scalars(stmt))

    def recall(self, organization_id: uuid.UUID, terms: list[str], *, limit: int = 8) -> list[BrainKnowledgeNode]:
        """Rank nodes by how many query terms appear in title/summary/type."""
        nodes = self.list_nodes(organization_id, limit=1000)
        lowered = [t.lower() for t in terms if len(t) > 2]
        scored: list[tuple[float, BrainKnowledgeNode]] = []
        for n in nodes:
            blob = f"{n.title} {n.summary} {n.node_type}".lower()
            hits = sum(1 for t in lowered if t in blob)
            if hits:
                scored.append((hits + n.confidence_score, n))
        scored.sort(key=lambda s: s[0], reverse=True)
        return [n for _, n in scored[:limit]]

    def by_source(self, organization_id: uuid.UUID, source_type: str, source_id: str | None = None) -> list[BrainKnowledgeNode]:
        stmt = select(BrainKnowledgeNode).where(
            BrainKnowledgeNode.organization_id == organization_id,
            BrainKnowledgeNode.source_type == source_type,
        )
        if source_id is not None:
            stmt = stmt.where(BrainKnowledgeNode.source_id == source_id)
        return list(self.db.scalars(stmt))

    def neighborhood(self, node_id: uuid.UUID, organization_id: uuid.UUID) -> dict:
        node = self.get_node(node_id, organization_id)
        edges = list(
            self.db.scalars(
                select(BrainKnowledgeEdge).where(
                    BrainKnowledgeEdge.organization_id == organization_id,
                    or_(
                        BrainKnowledgeEdge.from_node_id == node_id,
                        BrainKnowledgeEdge.to_node_id == node_id,
                    ),
                )
            )
        )
        neighbor_ids = {e.from_node_id for e in edges} | {e.to_node_id for e in edges}
        neighbor_ids.discard(node_id)
        neighbors = []
        if neighbor_ids:
            neighbors = list(
                self.db.scalars(
                    select(BrainKnowledgeNode).where(
                        BrainKnowledgeNode.organization_id == organization_id,
                        BrainKnowledgeNode.id.in_(neighbor_ids),
                    )
                )
            )
        return {"node": node, "edges": edges, "neighbors": neighbors}

    def stale_nodes(
        self, organization_id: uuid.UUID, *, older_than_days: int = STALE_AFTER_DAYS, limit: int = 200
    ) -> list[BrainKnowledgeNode]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        results = []
        for n in self.list_nodes(organization_id, limit=limit):
            updated = n.updated_at
            if updated is not None and updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            if updated is None or updated < cutoff:
                results.append(n)
        return results

    @staticmethod
    def is_stale(node: BrainKnowledgeNode, *, older_than_days: int = STALE_AFTER_DAYS) -> bool:
        updated = node.updated_at
        if updated is None:
            return True
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        return updated < datetime.now(timezone.utc) - timedelta(days=older_than_days)
