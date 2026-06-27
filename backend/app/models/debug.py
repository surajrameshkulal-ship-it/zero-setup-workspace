from __future__ import annotations
import uuid

from sqlalchemy import Float, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

# Recognized failure classifications.
FAILURE_TYPES = (
    "test_failure",
    "build_failure",
    "lint_failure",
    "runtime_error",
    "dependency_error",
    "configuration_error",
    "migration_error",
    "webhook_error",
    "ai_provider_error",
    "workspace_failure",
)


class DebugFailure(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A classified failure (from pasted logs or ingested system records).

    Read-only diagnosis input: storing a failure never edits code, runs anything,
    or writes to GitHub. Raw logs are secret-redacted on write.
    """

    __tablename__ = "debug_failures"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    failure_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)  # manual|validation|workspace|...
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    raw_log: Mapped[str] = mapped_column(Text, nullable=False, default="")
    signature: Mapped[str] = mapped_column(String(256), nullable=False, default="", index=True)
    affected_files: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    affected_services: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")

    diagnoses = relationship(
        "DebugDiagnosis", back_populates="failure", cascade="all, delete-orphan", order_by="DebugDiagnosis.created_at"
    )


class DebugDiagnosis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A senior-engineer-style root-cause analysis of a DebugFailure."""

    __tablename__ = "debug_diagnoses"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    failure_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("debug_failures.id", ondelete="CASCADE"), nullable=False, index=True
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    probable_cause: Mapped[str] = mapped_column(Text, nullable=False, default="")
    affected_files: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    affected_services: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # [{"id": str, "node_type": str, "title": str}]
    related_graph_nodes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    recommended_fix: Mapped[str] = mapped_column(Text, nullable=False, default="")

    failure = relationship("DebugFailure", back_populates="diagnoses")
