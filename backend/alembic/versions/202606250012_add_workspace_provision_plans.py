from __future__ import annotations
"""add repository_workspace_provision_plans

Revision ID: 202606250012
Revises: 202606250011
Create Date: 2026-06-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202606250012"
down_revision: Union[str, None] = "202606250011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "repository_workspace_provision_plans",
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
        sa.Column("language", sa.String(length=64), nullable=True),
        sa.Column("runtime", sa.String(length=64), nullable=True),
        sa.Column("runtime_version", sa.String(length=64), nullable=True),
        sa.Column("package_manager", sa.String(length=64), nullable=True),
        sa.Column("framework", sa.String(length=64), nullable=True),
        sa.Column("workspace_directory", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("environment_preparation", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("container_preparation", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("dependency_plan", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("startup_plan", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("validation", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("readiness_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recommendations", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("warnings", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("safety", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_repository_workspace_provision_plans_organization_id",
        "repository_workspace_provision_plans",
        ["organization_id"],
    )
    op.create_index(
        "ix_repository_workspace_provision_plans_repository_id",
        "repository_workspace_provision_plans",
        ["repository_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_repository_workspace_provision_plans_repository_id",
        table_name="repository_workspace_provision_plans",
    )
    op.drop_index(
        "ix_repository_workspace_provision_plans_organization_id",
        table_name="repository_workspace_provision_plans",
    )
    op.drop_table("repository_workspace_provision_plans")
