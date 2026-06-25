from __future__ import annotations
import enum
import uuid

from sqlalchemy import Enum, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.scan import RiskLevel


class RequestType(str, enum.Enum):
    BUG = "bug"
    FEATURE = "feature"
    REFACTOR = "refactor"
    DOCS = "docs"
    SECURITY = "security"
    PERFORMANCE = "performance"
    OTHER = "other"


class RequestStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    ANALYZING = "analyzing"
    PLAN_READY = "plan_ready"
    APPROVED = "approved"
    REJECTED = "rejected"
    IN_PROGRESS = "in_progress"
    PR_OPENED = "pr_opened"
    COMPLETED = "completed"
    FAILED = "failed"


class RequestPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [item.value for item in enum_cls]


class EngineeringRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An intake record for the AI Engineering Agent.

    The agent only ever produces a *plan*. It never deploys, merges, or pushes;
    every change must flow through human approval and a GitHub pull request.
    """

    __tablename__ = "engineering_requests"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    request_type: Mapped[RequestType] = mapped_column(
        Enum(RequestType, name="engineering_request_type", values_callable=_enum_values),
        nullable=False,
        default=RequestType.OTHER,
    )
    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus, name="engineering_request_status", values_callable=_enum_values),
        nullable=False,
        default=RequestStatus.SUBMITTED,
        index=True,
    )
    priority: Mapped[RequestPriority] = mapped_column(
        Enum(RequestPriority, name="engineering_request_priority", values_callable=_enum_values),
        nullable=False,
        default=RequestPriority.MEDIUM,
    )

    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_files: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    implementation_plan: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    test_plan: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    risk_level: Mapped[RiskLevel | None] = mapped_column(
        Enum(RiskLevel, name="risk_level", values_callable=_enum_values),
        nullable=True,
    )
    # Structured safety record, e.g.
    # {"allowed": [...], "forbidden": [...], "notes": [...]}
    safety_notes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    organization = relationship("Organization", back_populates="engineering_requests")
    repository = relationship("Repository")
    created_by = relationship("User")

    @property
    def repository_full_name(self) -> str | None:
        return self.repository.full_name if self.repository else None
