from __future__ import annotations
import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class BrainStepRead(ORMModel):
    id: uuid.UUID
    brain: str
    order: int
    status: str
    summary: str
    confidence: float
    evidence: list
    created_at: datetime


class BrainRunRead(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    conversation_id: uuid.UUID | None
    question: str
    status: str
    primary_brain: str | None
    brains_consulted: list
    confidence_score: float
    answer: str | None
    evidence: list
    suggested_actions: list
    created_at: datetime
    updated_at: datetime
    steps: list[BrainStepRead] = []


class BrainMessageRead(ORMModel):
    id: uuid.UUID
    role: str
    content: str
    run_id: uuid.UUID | None
    created_at: datetime


class BrainConversationRead(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class BrainConversationDetail(BrainConversationRead):
    messages: list[BrainMessageRead] = []


class BrainMemoryRead(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    kind: str
    title: str
    content: str
    tags: list
    source: str | None
    refs: list
    created_at: datetime
    updated_at: datetime


class BrainDecisionRead(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    run_id: uuid.UUID | None
    title: str
    decision: str
    rationale: str | None
    confidence: float
    evidence: list
    created_at: datetime


# -- request bodies -----------------------------------------------------------


class BrainAskRequest(BaseModel):
    question: str
    conversation_id: uuid.UUID | None = None


class BrainMemoryCreate(BaseModel):
    kind: str = "note"
    title: str
    content: str = ""
    tags: list[str] = []
    source: str | None = None
    refs: list = []
