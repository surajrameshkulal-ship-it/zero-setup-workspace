from __future__ import annotations
import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ScanStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PullRequestScan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "pull_request_scans"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    github_pr_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    github_pr_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    head_sha: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    base_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    github_check_run_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    status: Mapped[ScanStatus] = mapped_column(
        Enum(ScanStatus, name="scan_status", values_callable=lambda enum: [item.value for item in enum]),
        nullable=False,
        default=ScanStatus.QUEUED,
        index=True,
    )
    trigger: Mapped[str] = mapped_column(String(40), nullable=False, default="webhook")
    files_changed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lines_added: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lines_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_level: Mapped[RiskLevel | None] = mapped_column(
        Enum(RiskLevel, name="risk_level", values_callable=lambda enum: [item.value for item in enum]),
        nullable=True,
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    semgrep_findings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    ai_findings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    company_rule_violations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    architecture_violations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    report: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization = relationship("Organization", back_populates="scans")
    repository = relationship("Repository", back_populates="scans")

    @property
    def repository_full_name(self) -> str | None:
        return self.repository.full_name if self.repository else None

    @property
    def findings_count(self) -> int:
        return sum(
            len(findings or [])
            for findings in (
                self.semgrep_findings,
                self.ai_findings,
                self.company_rule_violations,
                self.architecture_violations,
            )
        )
