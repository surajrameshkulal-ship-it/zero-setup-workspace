from __future__ import annotations
"""add repository_setup_intents

Revision ID: 202606250009
Revises: 202606250008
Create Date: 2026-06-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202606250009"
down_revision: Union[str, None] = "202606250008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "repository_setup_intents",
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
        sa.Column("package_manager", sa.String(length=64), nullable=True),
        sa.Column("runtime_version", sa.String(length=64), nullable=True),
        sa.Column("install_command", sa.String(length=512), nullable=True),
        sa.Column("dev_command", sa.String(length=512), nullable=True),
        sa.Column("prod_command", sa.String(length=512), nullable=True),
        sa.Column("test_command", sa.String(length=512), nullable=True),
        sa.Column("build_command", sa.String(length=512), nullable=True),
        sa.Column("lint_command", sa.String(length=512), nullable=True),
        sa.Column("env_vars", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("ports", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("databases", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("caches", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("queues", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("external_services", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("docker", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("cicd_provider", sa.String(length=64), nullable=True),
        sa.Column("health_check_endpoint", sa.String(length=256), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("sources_analyzed", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("notes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_repository_setup_intents_organization_id", "repository_setup_intents", ["organization_id"])
    op.create_index(
        "ix_repository_setup_intents_repository_id", "repository_setup_intents", ["repository_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_repository_setup_intents_repository_id", table_name="repository_setup_intents")
    op.drop_index("ix_repository_setup_intents_organization_id", table_name="repository_setup_intents")
    op.drop_table("repository_setup_intents")
