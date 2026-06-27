from __future__ import annotations
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.database import get_db
from app.models.user import User
from app.schemas.brain import (
    BrainAskRequest,
    BrainConversationDetail,
    BrainConversationRead,
    BrainDecisionRead,
    BrainMemoryCreate,
    BrainMemoryRead,
    BrainRunRead,
)
from app.services.brain.memory_service import BrainMemoryService
from app.services.brain.super_brain import SuperBrainOrchestrator

# Internal/admin-only: the Super Brain is a privileged operator surface.
router = APIRouter(prefix="/brain", tags=["brain"], dependencies=[Depends(require_admin)])


@router.post("/ask", response_model=BrainRunRead)
def brain_ask(
    payload: BrainAskRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return SuperBrainOrchestrator(db).ask(
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        question=payload.question,
        conversation_id=payload.conversation_id,
    )


@router.get("/conversations", response_model=list[BrainConversationRead])
def brain_conversations(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return SuperBrainOrchestrator(db).list_conversations(current_user.organization_id)


@router.get("/conversations/{conversation_id}", response_model=BrainConversationDetail)
def brain_conversation_detail(
    conversation_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return SuperBrainOrchestrator(db).get_conversation(conversation_id, current_user.organization_id)


@router.get("/runs/{run_id}", response_model=BrainRunRead)
def brain_run(
    run_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return SuperBrainOrchestrator(db).get_run(run_id, current_user.organization_id)


@router.get("/memory", response_model=list[BrainMemoryRead])
def brain_memory_list(
    query: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return BrainMemoryService(db).list(current_user.organization_id, query=query, kind=kind)


@router.post("/memory", response_model=BrainMemoryRead, status_code=201)
def brain_memory_create(
    payload: BrainMemoryCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return BrainMemoryService(db).create(
        organization_id=current_user.organization_id,
        kind=payload.kind,
        title=payload.title,
        content=payload.content,
        tags=payload.tags,
        source=payload.source or "manual",
        refs=payload.refs,
        created_by_user_id=current_user.id,
    )


@router.get("/decisions", response_model=list[BrainDecisionRead])
def brain_decisions(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return BrainMemoryService(db).list_decisions(current_user.organization_id)
