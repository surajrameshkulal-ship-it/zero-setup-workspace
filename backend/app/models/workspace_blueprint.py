from __future__ import annotations
import uuid

from sqlalchemy import ForeignKey, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class WorkspaceBlueprint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A complete, reproducible workspace blueprint derived from the EnvironmentSpec.

    Planning/generation only: building a blueprint never launches containers,
    executes repository code, installs dependencies, runs Docker, starts
    processes, creates cloud resources, modifies the repository, or exposes
    secrets (only variable names are stored). All sequences are plans, not runs.
    """

    __tablename__ = "repository_workspace_blueprints"

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
    language: Mapped[str | None] = mapped_column(String(64), nullable=True)
    runtime: Mapped[str | None] = mapped_column(String(64), nullable=True)
    runtime_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    package_manager: Mapped[str | None] = mapped_column(String(64), nullable=True)
    framework: Mapped[str | None] = mapped_column(String(64), nullable=True)

    workspace_structure: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    environment_files: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    docker_assets: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    ide_assets: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    startup_plan: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    workspace_resources: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    readiness_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recommendations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    safety: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    organization = relationship("Organization", back_populates="workspace_blueprints")
    repository = relationship("Repository")

    @property
    def repository_full_name(self) -> str | None:
        return self.repository.full_name if self.repository else None
