from __future__ import annotations
import uuid

from sqlalchemy import Boolean, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class DraftPullRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Draft pull-request METADATA for an approved engineering request.

    This describes the pull request that a human could open. CodeDNA never
    pushes the branch, opens the PR, merges, or deploys. `is_pushed` is always
    False in this phase and all GitHub operations remain human-gated.
    """

    __tablename__ = "draft_pull_requests"

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

    branch_name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    # [{"order": int, "message": str, "files": [str]}]
    commit_plan: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    labels: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    # Always False in this phase: the agent never pushes or opens PRs.
    is_pushed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    human_approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    organization = relationship("Organization", back_populates="draft_pull_requests")
    engineering_request = relationship("EngineeringRequest")
    repository = relationship("Repository")
