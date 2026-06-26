from __future__ import annotations
import uuid

from sqlalchemy import Boolean, Float, ForeignKey, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class EnvironmentSpec(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A normalized, executable-later workspace blueprint derived from Setup Intent.

    This is a SPECIFICATION only. Generating it never executes repository code,
    installs dependencies, launches anything, or reads environment values — only
    variable names. The only network use is the existing read-only GitHub
    manifest fetch performed when producing the underlying Setup Intent.
    """

    __tablename__ = "repository_environment_specs"

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

    # Runtime
    primary_language: Mapped[str | None] = mapped_column(String(64), nullable=True)
    runtime_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    runtime_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    package_manager: Mapped[str | None] = mapped_column(String(64), nullable=True)
    framework: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Commands
    install_command: Mapped[str | None] = mapped_column(String(512), nullable=True)
    dev_command: Mapped[str | None] = mapped_column(String(512), nullable=True)
    prod_command: Mapped[str | None] = mapped_column(String(512), nullable=True)
    build_command: Mapped[str | None] = mapped_column(String(512), nullable=True)
    test_command: Mapped[str | None] = mapped_column(String(512), nullable=True)
    lint_command: Mapped[str | None] = mapped_column(String(512), nullable=True)
    health_check_command: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Services
    databases: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    caches: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    queues: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    external_services: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Ports
    app_ports: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    service_ports: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    health_check_endpoint: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Environment variables: [{"name": str, "required": bool}]
    env_vars: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    missing_env_example: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Strategy + resources
    container_strategy: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    workspace_requirements: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    safety: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Confidence / diagnostics
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    assumptions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    missing_information: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    organization = relationship("Organization", back_populates="environment_specs")
    repository = relationship("Repository")

    @property
    def repository_full_name(self) -> str | None:
        return self.repository.full_name if self.repository else None
