from __future__ import annotations
import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

# Lifecycle states for a real running sandbox.
WORKSPACE_STATUSES = (
    "pending",
    "provisioning",
    "installing",
    "starting",
    "running",
    "failed",
    "stopped",
    "cancelled",
    "crashed",
)

# States in which a repository is considered to already have an active launch.
ACTIVE_STATUSES = ("pending", "provisioning", "installing", "starting", "running")
# States that can still be cancelled (i.e. not yet running and not terminal).
CANCELLABLE_STATUSES = ("pending", "provisioning", "installing", "starting")
TERMINAL_STATUSES = ("failed", "stopped", "cancelled", "crashed")


class WorkspaceInstance(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A real, running sandbox instance launched from a Workspace Provision plan.

    Unlike the read-only planning artifacts, this models an actual lifecycle:
    the repository is fetched into an isolated workspace directory, dependencies
    are installed, the runtime command is started as a subprocess, readiness is
    probed, and logs/errors are captured. It is constrained to an isolated
    workspace base directory, runs with timeouts, and never modifies the real
    repository or performs any GitHub write.
    """

    __tablename__ = "workspace_instances"

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
    scan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pull_request_scans.id", ondelete="SET NULL"),
        nullable=True,
    )
    environment_spec_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    blueprint_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    provision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    runtime: Mapped[str | None] = mapped_column(String(64), nullable=True)
    workspace_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    install_command: Mapped[str | None] = mapped_column(String(512), nullable=True)
    runtime_command: Mapped[str | None] = mapped_column(String(512), nullable=True)
    preview_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    exposed_ports: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # [{"stream": "install"|"start"|"system", "message": str}]
    logs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stopped_at: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Structured event timeline: [{"event": str, "at": iso, "detail": str|None}]
    events: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Liveness / control.
    last_heartbeat_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    running_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recovery_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Resource limits (best-effort for local dev; full isolation arrives with
    # containers in Phase 11.2).
    cpu_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_limit_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    execution_timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=1800)

    # Metrics (milliseconds).
    install_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    startup_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    launch_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    organization = relationship("Organization", back_populates="workspace_instances")
    repository = relationship("Repository")

    @property
    def repository_full_name(self) -> str | None:
        return self.repository.full_name if self.repository else None
