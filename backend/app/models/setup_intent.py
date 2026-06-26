from __future__ import annotations
import uuid

from sqlalchemy import Float, ForeignKey, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class SetupIntent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """How a repository should be built and run, inferred read-only from manifests.

    Deterministic heuristics over README/package.json/pyproject/Dockerfile/etc.
    (reusing Repository DNA where useful). Repository code is never executed and
    environment values are never captured — only variable names.
    """

    __tablename__ = "repository_setup_intents"

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

    languages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    frameworks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    package_manager: Mapped[str | None] = mapped_column(String(64), nullable=True)
    runtime_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    install_command: Mapped[str | None] = mapped_column(String(512), nullable=True)
    dev_command: Mapped[str | None] = mapped_column(String(512), nullable=True)
    prod_command: Mapped[str | None] = mapped_column(String(512), nullable=True)
    test_command: Mapped[str | None] = mapped_column(String(512), nullable=True)
    build_command: Mapped[str | None] = mapped_column(String(512), nullable=True)
    lint_command: Mapped[str | None] = mapped_column(String(512), nullable=True)

    env_vars: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    ports: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    databases: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    caches: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    queues: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    external_services: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    docker: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    cicd_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    health_check_endpoint: Mapped[str | None] = mapped_column(String(256), nullable=True)

    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sources_analyzed: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    notes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    organization = relationship("Organization", back_populates="setup_intents")
    repository = relationship("Repository")

    @property
    def repository_full_name(self) -> str | None:
        return self.repository.full_name if self.repository else None
