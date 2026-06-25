from __future__ import annotations
"""add scan idempotency key

Revision ID: 202606240001
Revises: 202606230002
Create Date: 2026-06-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202606240001"
down_revision: Union[str, None] = "202606230002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pull_request_scans", sa.Column("idempotency_key", sa.String(length=128), nullable=True))
    op.create_index(
        "ix_pull_request_scans_idempotency_key",
        "pull_request_scans",
        ["idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_pull_request_scans_idempotency_key", table_name="pull_request_scans")
    op.drop_column("pull_request_scans", "idempotency_key")
