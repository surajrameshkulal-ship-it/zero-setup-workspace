from __future__ import annotations
import uuid

from sqlalchemy import ForeignKey, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ValidationRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Result of running the autonomous validation pipeline for a request.

    The pipeline runs validators (tests, build, Semgrep, CodeDNA review,
    company & architecture rules), optionally attempts automatic fixes, and
    retries up to a limit. On success it produces a *draft* pull request
    (metadata only). It never merges or deploys.
    """

    __tablename__ = "validation_runs"

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
    draft_pull_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("draft_pull_requests.id", ondelete="SET NULL"),
        nullable=True,
    )

    # passed | failed
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="failed")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    # [{"name": str, "status": "passed|failed|skipped", "details": str, "attempt": int}]
    checks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    auto_fixes_applied: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    report: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    organization = relationship("Organization", back_populates="validation_runs")
    engineering_request = relationship("EngineeringRequest")
    repository = relationship("Repository")
