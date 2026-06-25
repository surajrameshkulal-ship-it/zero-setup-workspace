from __future__ import annotations
"""add draft_pull_requests

Revision ID: 202606250005
Revises: 202606250004
Create Date: 2026-06-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202606250005"
down_revision: Union[str, None] = "202606250004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "draft_pull_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "engineering_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("engineering_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "repository_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repositories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("branch_name", sa.String(length=255), nullable=False),
        sa.Column("base_branch", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("commit_plan", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("labels", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("is_pushed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("human_approval_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_draft_pull_requests_organization_id", "draft_pull_requests", ["organization_id"])
    op.create_index(
        "ix_draft_pull_requests_engineering_request_id",
        "draft_pull_requests",
        ["engineering_request_id"],
        unique=True,
    )
    op.create_index("ix_draft_pull_requests_repository_id", "draft_pull_requests", ["repository_id"])


def downgrade() -> None:
    op.drop_index("ix_draft_pull_requests_repository_id", table_name="draft_pull_requests")
    op.drop_index("ix_draft_pull_requests_engineering_request_id", table_name="draft_pull_requests")
    op.drop_index("ix_draft_pull_requests_organization_id", table_name="draft_pull_requests")
    op.drop_table("draft_pull_requests")
