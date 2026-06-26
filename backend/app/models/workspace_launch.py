from __future__ import annotations
import uuid

from sqlalchemy import ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class WorkspaceLaunch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A launched, isolated local sandbox for a repository (Phase 11, Step 5).

    Launching is human-initiated. The sandbox is strongly isolated: source is
    mounted read-only, secrets/.env/.git are never materialized, CPU/memory/PID
    quotas and a TTL (auto-cleanup) are enforced, and network egress is
    restricted. The sandbox NEVER merges, deploys, pushes, or modifies the real
    repository — it only runs the project locally for inspection.
    """

    __tablename__ = "repository_workspace_launches"

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
        unique=True,
        index=True,
    )

    # pending | launching | running | healthy | unhealthy | stopped | failed | expired
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    runtime: Mapped[str | None] = mapped_column(String(64), nullable=True)
    image: Mapped[str | None] = mapped_column(String(256), nullable=True)
    start_command: Mapped[str | None] = mapped_column(String(512), nullable=True)
    container_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    published_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # [{"host": int, "container": int}]
    port_mappings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    health_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    health_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    logs_tail: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    resource_limits: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    # ISO-8601 strings (kept as JSON to avoid tz/driver friction across sqlite/pg)
    started_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stopped_at: Mapped[str | None] = mapped_column(String(64), nullable=True)

    safety: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    organization = relationship("Organization", back_populates="workspace_launches")
    repository = relationship("Repository")

    @property
    def repository_full_name(self) -> str | None:
        return self.repository.full_name if self.repository else None
