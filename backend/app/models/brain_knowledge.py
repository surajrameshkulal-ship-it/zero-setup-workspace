from __future__ import annotations
import uuid

from sqlalchemy import Float, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

# Reference vocabularies (not DB-enforced, kept flexible for new sources).
NODE_TYPES = (
    "phase", "feature", "module", "service", "model", "endpoint", "migration",
    "test", "decision", "blocker", "risk", "workspace", "repository", "integration",
    "audit",
)
EDGE_TYPES = (
    "depends_on", "implements", "uses", "owns", "caused_by", "fixed_by", "blocks",
    "related_to", "supersedes", "validates", "exposes", "belongs_to",
)


class BrainKnowledgeNode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A persistent unit of product knowledge in the Super Brain graph."""

    __tablename__ = "brain_knowledge_nodes"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "node_type", "source_type", "source_id",
            name="uq_brain_knowledge_node_source",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    # DB column is "node_metadata"; exposed as "metadata" in the API schema.
    node_metadata: Mapped[dict] = mapped_column("node_metadata", JSON, nullable=False, default=dict)


class BrainKnowledgeEdge(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A typed, evidence-bearing relationship between two knowledge nodes."""

    __tablename__ = "brain_knowledge_edges"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "from_node_id", "to_node_id", "relationship_type",
            name="uq_brain_knowledge_edge",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brain_knowledge_nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    to_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brain_knowledge_nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relationship_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    from_node = relationship("BrainKnowledgeNode", foreign_keys=[from_node_id])
    to_node = relationship("BrainKnowledgeNode", foreign_keys=[to_node_id])
