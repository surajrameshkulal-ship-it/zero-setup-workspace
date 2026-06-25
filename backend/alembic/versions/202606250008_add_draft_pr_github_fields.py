from __future__ import annotations
"""add github fields to draft_pull_requests

Revision ID: 202606250008
Revises: 202606250007
Create Date: 2026-06-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202606250008"
down_revision: Union[str, None] = "202606250007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("draft_pull_requests", sa.Column("github_pr_number", sa.Integer(), nullable=True))
    op.add_column("draft_pull_requests", sa.Column("github_pr_url", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    op.drop_column("draft_pull_requests", "github_pr_url")
    op.drop_column("draft_pull_requests", "github_pr_number")
