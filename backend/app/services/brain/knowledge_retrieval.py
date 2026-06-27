"""KnowledgeRetrievalService — read-only retrieval over the knowledge graph.

The companion to KnowledgeIngestionService: ingestion writes the graph, this
service reads it. Pure retrieval — keyword search, term recall, graph search
(keyword hits expanded through their neighborhoods), source lookup, neighborhood
lookup, confidence filtering, and stale detection. It never writes, executes
code, or touches GitHub. Organization-scoped throughout; it delegates storage
concerns to KnowledgeGraphService so the read and write surfaces stay separate.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.brain_knowledge import BrainKnowledgeNode
from app.services.brain.knowledge_service import KnowledgeGraphService

MIN_TERM_LEN = 3


class KnowledgeRetrievalService:
    def __init__(self, db: Session, *, graph: KnowledgeGraphService | None = None) -> None:
        self.db = db
        self.graph = graph or KnowledgeGraphService(db)

    # -- direct retrieval (delegated) -----------------------------------------

    def get_node(self, node_id: uuid.UUID, organization_id: uuid.UUID) -> BrainKnowledgeNode:
        return self.graph.get_node(node_id, organization_id)

    def list_nodes(
        self,
        organization_id: uuid.UUID,
        *,
        node_type: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 200,
    ) -> list[BrainKnowledgeNode]:
        return self.graph.list_nodes(
            organization_id, node_type=node_type, min_confidence=min_confidence, limit=limit
        )

    def search(
        self,
        organization_id: uuid.UUID,
        query: str,
        *,
        node_type: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 20,
    ) -> list[BrainKnowledgeNode]:
        return self.graph.search(
            organization_id, query, node_type=node_type, min_confidence=min_confidence, limit=limit
        )

    def recall(self, organization_id: uuid.UUID, terms: list[str], *, limit: int = 8) -> list[BrainKnowledgeNode]:
        return self.graph.recall(organization_id, terms, limit=limit)

    def by_source(
        self, organization_id: uuid.UUID, source_type: str, source_id: str | None = None
    ) -> list[BrainKnowledgeNode]:
        return self.graph.by_source(organization_id, source_type, source_id)

    def neighborhood(self, node_id: uuid.UUID, organization_id: uuid.UUID) -> dict:
        return self.graph.neighborhood(node_id, organization_id)

    def stale_nodes(self, organization_id: uuid.UUID, *, older_than_days: int | None = None, limit: int = 200):
        kwargs = {"limit": limit}
        if older_than_days is not None:
            kwargs["older_than_days"] = older_than_days
        return self.graph.stale_nodes(organization_id, **kwargs)

    @staticmethod
    def is_stale(node: BrainKnowledgeNode, *, older_than_days: int | None = None) -> bool:
        if older_than_days is None:
            return KnowledgeGraphService.is_stale(node)
        return KnowledgeGraphService.is_stale(node, older_than_days=older_than_days)

    # -- higher-level retrieval -----------------------------------------------

    @staticmethod
    def _terms(question: str | None) -> list[str]:
        return [w.strip(".,?!:;()[]") for w in (question or "").split() if len(w.strip(".,?!:;()[]")) > MIN_TERM_LEN]

    def recall_for_question(
        self, organization_id: uuid.UUID, question: str | None, *, limit: int = 8
    ) -> list[BrainKnowledgeNode]:
        """Recall nodes relevant to a free-text question (the brains' entry point)."""
        terms = self._terms(question)
        if not terms:
            return []
        return self.graph.recall(organization_id, terms, limit=limit)

    def graph_search(
        self, organization_id: uuid.UUID, query: str, *, limit: int = 10, expand: bool = True, expand_from: int = 5
    ) -> dict:
        """Keyword search, optionally expanded with the neighbors of the top hits.

        Returns {"matches": [...], "related": [...]} where related nodes are
        distinct from the direct matches — the one-hop neighborhood of the
        strongest results, so callers get connected context, not just keyword hits.
        """
        matches = self.graph.search(organization_id, query, limit=limit)
        related: list[BrainKnowledgeNode] = []
        if expand and matches:
            seen = {m.id for m in matches}
            for hit in matches[:expand_from]:
                for neighbor in self.graph.neighborhood(hit.id, organization_id)["neighbors"]:
                    if neighbor.id not in seen:
                        seen.add(neighbor.id)
                        related.append(neighbor)
        return {"matches": matches, "related": related}
