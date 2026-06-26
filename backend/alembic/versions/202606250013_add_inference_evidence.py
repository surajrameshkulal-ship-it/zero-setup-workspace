from __future__ import annotations
"""add evidence to setup intents and environment specs

Revision ID: 202606250013
Revises: 202606250012
Create Date: 2026-06-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202606250013"
down_revision: Union[str, None] = "202606250012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "repository_setup_intents",
        sa.Column("evidence", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "repository_environment_specs",
        sa.Column("evidence", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("repository_environment_specs", "evidence")
    op.drop_column("repository_setup_intents", "evidence")
