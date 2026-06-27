from __future__ import annotations
import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class DebugFailureRead(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    failure_type: str
    source: str | None
    source_ref: str | None
    title: str
    signature: str
    affected_files: list
    affected_services: list
    severity: str
    created_at: datetime
    updated_at: datetime


class DebugDiagnosisRead(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    failure_id: uuid.UUID
    summary: str
    probable_cause: str
    affected_files: list
    affected_services: list
    related_graph_nodes: list
    severity: str
    confidence_score: float
    evidence: list
    recommended_fix: str
    created_at: datetime
    failure: DebugFailureRead | None = None


class DebugFailureDetail(DebugFailureRead):
    raw_log: str
    diagnoses: list[DebugDiagnosisRead] = []


class DebugPattern(BaseModel):
    signature: str
    failure_type: str
    count: int
    example_title: str
    last_seen: str | None
    affected_files: list


class DiagnoseRequest(BaseModel):
    logs: str
    source: str = "manual"
    source_ref: str | None = None
