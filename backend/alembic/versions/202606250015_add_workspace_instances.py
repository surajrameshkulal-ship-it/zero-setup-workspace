from __future__ import annotations
"""add workspace_instances

Revision ID: 202606250015
Revises: 202606250014
Create Date: 2026-06-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202606250015"
down_revision: Union[str, None] = "202606250014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspace_instances",
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
        sa.Column(
            "scan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pull_request_scans.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("environment_spec_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("blueprint_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("runtime", sa.String(length=64), nullable=True),
        sa.Column("workspace_path", sa.String(length=1024), nullable=True),
        sa.Column("install_command", sa.String(length=512), nullable=True),
        sa.Column("runtime_command", sa.String(length=512), nullable=True),
        sa.Column("preview_url", sa.String(length=512), nullable=True),
        sa.Column("exposed_ports", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("logs", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("stopped_at", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_workspace_instances_organization_id", "workspace_instances", ["organization_id"])
    op.create_index("ix_workspace_instances_repository_id", "workspace_instances", ["repository_id"])


def downgrade() -> None:
    op.drop_index("ix_workspace_instances_repository_id", table_name="workspace_instances")
    op.drop_index("ix_workspace_instances_organization_id", table_name="workspace_instances")
    op.drop_table("workspace_instances")
