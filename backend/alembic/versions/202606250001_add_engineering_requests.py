from __future__ import annotations
"""add engineering_requests

Revision ID: 202606250001
Revises: 202606240001
Create Date: 2026-06-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202606250001"
down_revision: Union[str, None] = "202606240001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


REQUEST_TYPE = postgresql.ENUM(
    "bug", "feature", "refactor", "docs", "security", "performance", "other",
    name="engineering_request_type",
)
REQUEST_STATUS = postgresql.ENUM(
    "submitted", "analyzing", "plan_ready", "approved", "rejected",
    "in_progress", "pr_opened", "completed", "failed",
    name="engineering_request_status",
)
REQUEST_PRIORITY = postgresql.ENUM(
    "low", "medium", "high", "urgent",
    name="engineering_request_priority",
)
# risk_level already exists (created by the initial migration); reuse without re-creating.
RISK_LEVEL = postgresql.ENUM(
    "low", "medium", "high", "critical",
    name="risk_level",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    REQUEST_TYPE.create(bind, checkfirst=True)
    REQUEST_STATUS.create(bind, checkfirst=True)
    REQUEST_PRIORITY.create(bind, checkfirst=True)

    op.create_table(
        "engineering_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "repository_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repositories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("request_type", REQUEST_TYPE, nullable=False, server_default="other"),
        sa.Column("status", REQUEST_STATUS, nullable=False, server_default="submitted"),
        sa.Column("priority", REQUEST_PRIORITY, nullable=False, server_default="medium"),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("affected_files", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("implementation_plan", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("test_plan", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("risk_level", RISK_LEVEL, nullable=True),
        sa.Column("safety_notes", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_engineering_requests_organization_id",
        "engineering_requests",
        ["organization_id"],
    )
    op.create_index(
        "ix_engineering_requests_repository_id",
        "engineering_requests",
        ["repository_id"],
    )
    op.create_index(
        "ix_engineering_requests_created_by_user_id",
        "engineering_requests",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_engineering_requests_status",
        "engineering_requests",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_engineering_requests_status", table_name="engineering_requests")
    op.drop_index("ix_engineering_requests_created_by_user_id", table_name="engineering_requests")
    op.drop_index("ix_engineering_requests_repository_id", table_name="engineering_requests")
    op.drop_index("ix_engineering_requests_organization_id", table_name="engineering_requests")
    op.drop_table("engineering_requests")

    bind = op.get_bind()
    REQUEST_PRIORITY.drop(bind, checkfirst=True)
    REQUEST_STATUS.drop(bind, checkfirst=True)
    REQUEST_TYPE.drop(bind, checkfirst=True)
