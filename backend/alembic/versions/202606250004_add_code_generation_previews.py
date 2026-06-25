from __future__ import annotations
"""add code_generation_previews

Revision ID: 202606250004
Revises: 202606250003
Create Date: 2026-06-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202606250004"
down_revision: Union[str, None] = "202606250003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "code_generation_previews",
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
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("affected_files", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("diff_preview", sa.Text(), nullable=True),
        sa.Column("implementation_tasks", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("estimated_changes", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("documentation_updates", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("tests_to_create", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("ai_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_code_generation_previews_organization_id", "code_generation_previews", ["organization_id"]
    )
    op.create_index(
        "ix_code_generation_previews_engineering_request_id",
        "code_generation_previews",
        ["engineering_request_id"],
        unique=True,
    )
    op.create_index(
        "ix_code_generation_previews_repository_id", "code_generation_previews", ["repository_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_code_generation_previews_repository_id", table_name="code_generation_previews")
    op.drop_index(
        "ix_code_generation_previews_engineering_request_id", table_name="code_generation_previews"
    )
    op.drop_index("ix_code_generation_previews_organization_id", table_name="code_generation_previews")
    op.drop_table("code_generation_previews")
