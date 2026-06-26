from __future__ import annotations
"""harden workspace_instances: timeline, heartbeat, limits, metrics

Revision ID: 202606250016
Revises: 202606250015
Create Date: 2026-06-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202606250016"
down_revision: Union[str, None] = "202606250015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("workspace_instances", sa.Column("events", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("workspace_instances", sa.Column("last_heartbeat_at", sa.String(length=64), nullable=True))
    op.add_column("workspace_instances", sa.Column("running_at", sa.String(length=64), nullable=True))
    op.add_column("workspace_instances", sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("workspace_instances", sa.Column("recovery_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("workspace_instances", sa.Column("cpu_limit", sa.Float(), nullable=True))
    op.add_column("workspace_instances", sa.Column("memory_limit_mb", sa.Integer(), nullable=True))
    op.add_column(
        "workspace_instances",
        sa.Column("execution_timeout_seconds", sa.Integer(), nullable=False, server_default="1800"),
    )
    op.add_column("workspace_instances", sa.Column("install_duration_ms", sa.Integer(), nullable=True))
    op.add_column("workspace_instances", sa.Column("startup_duration_ms", sa.Integer(), nullable=True))
    op.add_column("workspace_instances", sa.Column("launch_duration_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    for col in (
        "launch_duration_ms",
        "startup_duration_ms",
        "install_duration_ms",
        "execution_timeout_seconds",
        "memory_limit_mb",
        "cpu_limit",
        "recovery_attempts",
        "cancel_requested",
        "running_at",
        "last_heartbeat_at",
        "events",
    ):
        op.drop_column("workspace_instances", col)
