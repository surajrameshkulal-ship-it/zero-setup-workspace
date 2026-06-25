from __future__ import annotations
import uuid

from sqlalchemy import ForeignKey, JSON, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class CodeGenerationPreview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A PREVIEW of proposed code changes for an approved engineering request.

    This is preview metadata only. Nothing here is written to disk, committed,
    pushed, branched, turned into a PR, or deployed. The diff is illustrative.
    """

    __tablename__ = "code_generation_previews"

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

    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # [{"path": str, "change_type": "modify|create|delete", "reason": str}]
    affected_files: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    diff_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    implementation_tasks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    estimated_changes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    documentation_updates: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    tests_to_create: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    ai_available: Mapped[bool] = mapped_column(default=False, nullable=False)

    organization = relationship("Organization", back_populates="code_generation_previews")
    engineering_request = relationship("EngineeringRequest")
    repository = relationship("Repository")
