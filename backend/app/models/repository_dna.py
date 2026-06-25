from __future__ import annotations
import uuid

from sqlalchemy import ForeignKey, JSON, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class RepositoryDNA(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A read-only "DNA" fingerprint of a repository.

    Derived entirely from CodeDNA's own data (repository metadata, scan findings,
    rules). It never clones the repository, reads source files directly, or
    performs any Git write. Everything here is inferred metadata.
    """

    __tablename__ = "repository_dna"

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
    package_managers: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    databases: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    queues: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    testing_tools: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    build_tools: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    cicd: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    docker: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    security_tools: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    important_files: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    architecture_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    dependency_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    repository_health: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    risk_notes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    organization = relationship("Organization", back_populates="repository_dna")
    repository = relationship("Repository")

    @property
    def repository_full_name(self) -> str | None:
        return self.repository.full_name if self.repository else None
