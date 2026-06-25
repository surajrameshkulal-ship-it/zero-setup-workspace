from __future__ import annotations
import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ExecutionRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tracks one human-gated AI execution pipeline for an engineering request.

    The orchestrator sequences existing Phase 10 services (materialize -> code
    generation -> safe apply (workspace only) -> validation -> draft PR). It
    never merges or deploys. One run per engineering request (resumable).
    """

    __tablename__ = "execution_runs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    engineering_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engineering_requests.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    # Deterministic, stable per request (idempotent retries map to the same run).
    execution_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    current_stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    completed_stages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancellation_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    workspace_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    target_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    code_plan: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    rollback_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    validation_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    draft_pull_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    report: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    organization = relationship("Organization", back_populates="execution_runs")
    engineering_request = relationship("EngineeringRequest")
