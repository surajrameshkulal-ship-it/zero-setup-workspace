from __future__ import annotations
"""add repository_workspace_launches

Revision ID: 202606250014
Revises: 202606250013
Create Date: 2026-06-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202606250014"
down_revision: Union[str, None] = "202606250013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "repository_workspace_launches",
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
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("runtime", sa.String(length=64), nullable=True),
        sa.Column("image", sa.String(length=256), nullable=True),
        sa.Column("start_command", sa.String(length=512), nullable=True),
        sa.Column("container_id", sa.String(length=128), nullable=True),
        sa.Column("published_url", sa.String(length=512), nullable=True),
        sa.Column("port_mappings", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("health_status", sa.String(length=32), nullable=True),
        sa.Column("health_detail", sa.Text(), nullable=True),
        sa.Column("logs_tail", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("resource_limits", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("ttl_seconds", sa.Integer(), nullable=False, server_default="3600"),
        sa.Column("started_at", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.String(length=64), nullable=True),
        sa.Column("stopped_at", sa.String(length=64), nullable=True),
        sa.Column("safety", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_repository_workspace_launches_organization_id",
        "repository_workspace_launches",
        ["organization_id"],
    )
    op.create_index(
        "ix_repository_workspace_launches_repository_id",
        "repository_workspace_launches",
        ["repository_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_repository_workspace_launches_repository_id", table_name="repository_workspace_launches")
    op.drop_index("ix_repository_workspace_launches_organization_id", table_name="repository_workspace_launches")
    op.drop_table("repository_workspace_launches")
