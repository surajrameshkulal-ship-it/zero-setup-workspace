from __future__ import annotations
"""add execution_runs

Revision ID: 202606250007
Revises: 202606250006
Create Date: 2026-06-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202606250007"
down_revision: Union[str, None] = "202606250006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "execution_runs",
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
        sa.Column("execution_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("current_stage", sa.String(length=40), nullable=True),
        sa.Column("completed_stages", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cancellation_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("workspace_path", sa.String(length=1024), nullable=True),
        sa.Column("target_branch", sa.String(length=255), nullable=True),
        sa.Column("default_branch", sa.String(length=255), nullable=True),
        sa.Column("code_plan", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("rollback_snapshot", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("validation_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("draft_pull_request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("report", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_execution_runs_organization_id", "execution_runs", ["organization_id"])
    op.create_index(
        "ix_execution_runs_engineering_request_id", "execution_runs", ["engineering_request_id"], unique=True
    )
    op.create_index("ix_execution_runs_execution_id", "execution_runs", ["execution_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_execution_runs_execution_id", table_name="execution_runs")
    op.drop_index("ix_execution_runs_engineering_request_id", table_name="execution_runs")
    op.drop_index("ix_execution_runs_organization_id", table_name="execution_runs")
    op.drop_table("execution_runs")
