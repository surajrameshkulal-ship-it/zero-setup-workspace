from __future__ import annotations
"""add repository_dna

Revision ID: 202606250003
Revises: 202606250002
Create Date: 2026-06-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202606250003"
down_revision: Union[str, None] = "202606250002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "repository_dna",
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
        sa.Column("languages", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("frameworks", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("package_managers", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("databases", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("queues", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("testing_tools", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("build_tools", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("cicd", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("docker", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("security_tools", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("important_files", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("architecture_summary", sa.Text(), nullable=True),
        sa.Column("dependency_summary", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("repository_health", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("risk_notes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_repository_dna_organization_id", "repository_dna", ["organization_id"])
    op.create_index("ix_repository_dna_repository_id", "repository_dna", ["repository_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_repository_dna_repository_id", table_name="repository_dna")
    op.drop_index("ix_repository_dna_organization_id", table_name="repository_dna")
    op.drop_table("repository_dna")
