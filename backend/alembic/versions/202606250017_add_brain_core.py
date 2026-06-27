from __future__ import annotations
"""add CodeDNA Super Brain core tables

Revision ID: 202606250017
Revises: 202606250016
Create Date: 2026-06-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202606250017"
down_revision: Union[str, None] = "202606250016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid():
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "brain_conversations",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("organization_id", _uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False, server_default="Conversation"),
        sa.Column("created_by_user_id", _uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_brain_conversations_organization_id", "brain_conversations", ["organization_id"])

    op.create_table(
        "brain_messages",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("conversation_id", _uuid(), sa.ForeignKey("brain_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("run_id", _uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_brain_messages_conversation_id", "brain_messages", ["conversation_id"])

    op.create_table(
        "brain_runs",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("organization_id", _uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", _uuid(), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column("primary_brain", sa.String(length=64), nullable=True),
        sa.Column("brains_consulted", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("suggested_actions", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_by_user_id", _uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_brain_runs_organization_id", "brain_runs", ["organization_id"])
    op.create_index("ix_brain_runs_conversation_id", "brain_runs", ["conversation_id"])

    op.create_table(
        "brain_steps",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("run_id", _uuid(), sa.ForeignKey("brain_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brain", sa.String(length=64), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_brain_steps_run_id", "brain_steps", ["run_id"])

    op.create_table(
        "brain_memory",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("organization_id", _uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False, server_default="note"),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("refs", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_by_user_id", _uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_brain_memory_organization_id", "brain_memory", ["organization_id"])

    op.create_table(
        "brain_decisions",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("organization_id", _uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", _uuid(), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False, server_default=""),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_brain_decisions_organization_id", "brain_decisions", ["organization_id"])


def downgrade() -> None:
    for table in (
        "brain_decisions",
        "brain_memory",
        "brain_steps",
        "brain_runs",
        "brain_messages",
        "brain_conversations",
    ):
        op.drop_table(table)
