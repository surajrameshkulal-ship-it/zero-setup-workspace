from __future__ import annotations
"""add brain knowledge graph (nodes + edges)

Revision ID: 202606250018
Revises: 202606250017
Create Date: 2026-06-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202606250018"
down_revision: Union[str, None] = "202606250017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid():
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "brain_knowledge_nodes",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("organization_id", _uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_type", sa.String(length=64), nullable=True),
        sa.Column("source_id", sa.String(length=128), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("node_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "organization_id", "node_type", "source_type", "source_id", name="uq_brain_knowledge_node_source"
        ),
    )
    op.create_index("ix_brain_knowledge_nodes_organization_id", "brain_knowledge_nodes", ["organization_id"])
    op.create_index("ix_brain_knowledge_nodes_node_type", "brain_knowledge_nodes", ["node_type"])

    op.create_table(
        "brain_knowledge_edges",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("organization_id", _uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_node_id", _uuid(), sa.ForeignKey("brain_knowledge_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_node_id", _uuid(), sa.ForeignKey("brain_knowledge_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relationship_type", sa.String(length=32), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "organization_id", "from_node_id", "to_node_id", "relationship_type", name="uq_brain_knowledge_edge"
        ),
    )
    op.create_index("ix_brain_knowledge_edges_organization_id", "brain_knowledge_edges", ["organization_id"])
    op.create_index("ix_brain_knowledge_edges_from_node_id", "brain_knowledge_edges", ["from_node_id"])
    op.create_index("ix_brain_knowledge_edges_to_node_id", "brain_knowledge_edges", ["to_node_id"])
    op.create_index("ix_brain_knowledge_edges_relationship_type", "brain_knowledge_edges", ["relationship_type"])


def downgrade() -> None:
    op.drop_table("brain_knowledge_edges")
    op.drop_table("brain_knowledge_nodes")
