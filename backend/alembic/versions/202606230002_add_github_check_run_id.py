from __future__ import annotations
"""add github check run id to scans

Revision ID: 202606230002
Revises: 202606230001
Create Date: 2026-06-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202606230002"
down_revision: Union[str, None] = "202606230001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pull_request_scans", sa.Column("github_check_run_id", sa.BigInteger(), nullable=True))
    op.create_index(
        "ix_pull_request_scans_github_check_run_id",
        "pull_request_scans",
        ["github_check_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_pull_request_scans_github_check_run_id", table_name="pull_request_scans")
    op.drop_column("pull_request_scans", "github_check_run_id")

