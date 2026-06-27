from __future__ import annotations
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeNodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    node_type: str
    title: str
    summary: str
    source_type: str | None
    source_id: str | None
    confidence_score: float
    # DB attribute is node_metadata; exposed as "metadata".
    metadata: dict = Field(default_factory=dict, validation_alias="node_metadata")
    created_at: datetime
    updated_at: datetime


class KnowledgeEdgeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_node_id: uuid.UUID
    to_node_id: uuid.UUID
    relationship_type: str
    confidence_score: float
    evidence: list
    created_at: datetime


class KnowledgeNeighbor(BaseModel):
    node: KnowledgeNodeRead
    edges: list[KnowledgeEdgeRead]
    neighbors: list[KnowledgeNodeRead]


class KnowledgeIngestResult(BaseModel):
    nodes: int
    edges: int
