from __future__ import annotations
"""add debug intelligence (failures + diagnoses)

Revision ID: 202606250019
Revises: 202606250018
Create Date: 2026-06-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202606250019"
down_revision: Union[str, None] = "202606250018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid():
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "debug_failures",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("organization_id", _uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("failure_type", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("raw_log", sa.Text(), nullable=False, server_default=""),
        sa.Column("signature", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("affected_files", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("affected_services", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="medium"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_debug_failures_organization_id", "debug_failures", ["organization_id"])
    op.create_index("ix_debug_failures_failure_type", "debug_failures", ["failure_type"])
    op.create_index("ix_debug_failures_signature", "debug_failures", ["signature"])

    op.create_table(
        "debug_diagnoses",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("organization_id", _uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("failure_id", _uuid(), sa.ForeignKey("debug_failures.id", ondelete="CASCADE"), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("probable_cause", sa.Text(), nullable=False, server_default=""),
        sa.Column("affected_files", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("affected_services", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("related_graph_nodes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="medium"),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("recommended_fix", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_debug_diagnoses_organization_id", "debug_diagnoses", ["organization_id"])
    op.create_index("ix_debug_diagnoses_failure_id", "debug_diagnoses", ["failure_id"])


def downgrade() -> None:
    op.drop_table("debug_diagnoses")
    op.drop_table("debug_failures")
