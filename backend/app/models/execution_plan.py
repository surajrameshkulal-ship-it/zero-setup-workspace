from __future__ import annotations
import enum
import uuid

from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ExecutionSafetyStatus(str, enum.Enum):
    SAFE = "safe"
    NEEDS_APPROVAL = "needs_approval"
    BLOCKED = "blocked"


class ExecutionComplexity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ExecutionPlan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Planning-only execution metadata for an approved engineering request.

    This record never contains source code and the framework never pushes,
    merges, or deploys. It exists so a human can review the proposed approach,
    impact, and safety posture before any future (separately gated) coding step.
    """

    __tablename__ = "execution_plans"

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
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Ordered implementation tasks: [{"order": int, "title": str, "detail": str}]
    tasks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    estimated_files: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    dependency_analysis: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    complexity: Mapped[str] = mapped_column(String(16), nullable=False, default=ExecutionComplexity.LOW.value)
    estimated_duration: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rollback_strategy: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    validation_checklist: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Normalized repository context object (no source code).
    repository_context: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Safety verdict: safe | needs_approval | blocked
    safety_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ExecutionSafetyStatus.NEEDS_APPROVAL.value
    )
    safety_findings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    branch_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    organization = relationship("Organization", back_populates="execution_plans")
    engineering_request = relationship("EngineeringRequest")
    repository = relationship("Repository")
