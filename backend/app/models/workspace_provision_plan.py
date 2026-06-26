from __future__ import annotations
import uuid

from sqlalchemy import ForeignKey, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class WorkspaceProvisionPlan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A preparation plan for a runnable workspace, derived from the blueprint.

    Preparation/planning only: generating it never starts Docker, runs compose,
    executes repository code, starts services/processes, deploys, creates cloud
    resources, installs dependencies, modifies the repository, or writes
    secrets. The only network use is the existing read-only GitHub metadata.
    All sequences are plans, not runs.
    """

    __tablename__ = "repository_workspace_provision_plans"

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

    # Runtime (carried from the blueprint)
    language: Mapped[str | None] = mapped_column(String(64), nullable=True)
    runtime: Mapped[str | None] = mapped_column(String(64), nullable=True)
    runtime_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    package_manager: Mapped[str | None] = mapped_column(String(64), nullable=True)
    framework: Mapped[str | None] = mapped_column(String(64), nullable=True)

    workspace_directory: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    environment_preparation: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    container_preparation: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    dependency_plan: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    startup_plan: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    validation: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    readiness_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recommendations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    safety: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    organization = relationship("Organization", back_populates="workspace_provision_plans")
    repository = relationship("Repository")

    @property
    def repository_full_name(self) -> str | None:
        return self.repository.full_name if self.repository else None
