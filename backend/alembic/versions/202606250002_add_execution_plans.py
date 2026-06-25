from __future__ import annotations
"""add execution_plans

Revision ID: 202606250002
Revises: 202606250001
Create Date: 2026-06-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202606250002"
down_revision: Union[str, None] = "202606250001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "execution_plans",
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
        sa.Column("tasks", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("estimated_files", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("dependency_analysis", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("complexity", sa.String(length=16), nullable=False, server_default="low"),
        sa.Column("estimated_duration", sa.String(length=64), nullable=True),
        sa.Column("rollback_strategy", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("validation_checklist", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("repository_context", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("safety_status", sa.String(length=32), nullable=False, server_default="needs_approval"),
        sa.Column("safety_findings", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("branch_name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_execution_plans_organization_id",
        "execution_plans",
        ["organization_id"],
    )
    op.create_index(
        "ix_execution_plans_engineering_request_id",
        "execution_plans",
        ["engineering_request_id"],
        unique=True,
    )
    op.create_index(
        "ix_execution_plans_repository_id",
        "execution_plans",
        ["repository_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_execution_plans_repository_id", table_name="execution_plans")
    op.drop_index("ix_execution_plans_engineering_request_id", table_name="execution_plans")
    op.drop_index("ix_execution_plans_organization_id", table_name="execution_plans")
    op.drop_table("execution_plans")
