from __future__ import annotations
"""add validation_runs

Revision ID: 202606250006
Revises: 202606250005
Create Date: 2026-06-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202606250006"
down_revision: Union[str, None] = "202606250005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "validation_runs",
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
        sa.Column(
            "draft_pull_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("draft_pull_requests.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="failed"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("checks", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("auto_fixes_applied", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("report", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_validation_runs_organization_id", "validation_runs", ["organization_id"])
    op.create_index(
        "ix_validation_runs_engineering_request_id",
        "validation_runs",
        ["engineering_request_id"],
        unique=True,
    )
    op.create_index("ix_validation_runs_repository_id", "validation_runs", ["repository_id"])


def downgrade() -> None:
    op.drop_index("ix_validation_runs_repository_id", table_name="validation_runs")
    op.drop_index("ix_validation_runs_engineering_request_id", table_name="validation_runs")
    op.drop_index("ix_validation_runs_organization_id", table_name="validation_runs")
    op.drop_table("validation_runs")
