from __future__ import annotations
"""add repository_environment_specs

Revision ID: 202606250010
Revises: 202606250009
Create Date: 2026-06-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202606250010"
down_revision: Union[str, None] = "202606250009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "repository_environment_specs",
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
        sa.Column("primary_language", sa.String(length=64), nullable=True),
        sa.Column("runtime_name", sa.String(length=64), nullable=True),
        sa.Column("runtime_version", sa.String(length=64), nullable=True),
        sa.Column("package_manager", sa.String(length=64), nullable=True),
        sa.Column("framework", sa.String(length=64), nullable=True),
        sa.Column("install_command", sa.String(length=512), nullable=True),
        sa.Column("dev_command", sa.String(length=512), nullable=True),
        sa.Column("prod_command", sa.String(length=512), nullable=True),
        sa.Column("build_command", sa.String(length=512), nullable=True),
        sa.Column("test_command", sa.String(length=512), nullable=True),
        sa.Column("lint_command", sa.String(length=512), nullable=True),
        sa.Column("health_check_command", sa.String(length=512), nullable=True),
        sa.Column("databases", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("caches", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("queues", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("external_services", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("app_ports", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("service_ports", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("health_check_endpoint", sa.String(length=256), nullable=True),
        sa.Column("env_vars", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("missing_env_example", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("container_strategy", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("workspace_requirements", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("safety", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("assumptions", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("missing_information", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("warnings", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_repository_environment_specs_organization_id", "repository_environment_specs", ["organization_id"]
    )
    op.create_index(
        "ix_repository_environment_specs_repository_id", "repository_environment_specs", ["repository_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_repository_environment_specs_repository_id", table_name="repository_environment_specs")
    op.drop_index("ix_repository_environment_specs_organization_id", table_name="repository_environment_specs")
    op.drop_table("repository_environment_specs")
