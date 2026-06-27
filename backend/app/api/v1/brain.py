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
from app.schemas.brain_knowledge import (
    KnowledgeIngestResult,
    KnowledgeNeighbor,
    KnowledgeNodeRead,
)
from app.schemas.engineering_intelligence import (
    ArchitectureReview,
    DependencyResult,
    EngineeringOverview,
    ImpactResult,
)
from app.schemas.debug import (
    DebugDiagnosisRead,
    DebugFailureDetail,
    DebugFailureRead,
    DebugPattern,
    DiagnoseRequest,
)
from app.services.brain.debug_intelligence import DebugIntelligenceService
from app.services.brain.engineering_intelligence import EngineeringIntelligenceService
from app.services.brain.knowledge_ingestion import KnowledgeIngestionService
from app.services.brain.knowledge_retrieval import KnowledgeRetrievalService
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


# -- knowledge graph (Phase 12.1) --------------------------------------------


@router.get("/knowledge/nodes", response_model=list[KnowledgeNodeRead])
def knowledge_nodes(
    node_type: str | None = Query(default=None),
    min_confidence: float = Query(default=0.0),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return KnowledgeRetrievalService(db).list_nodes(
        current_user.organization_id, node_type=node_type, min_confidence=min_confidence
    )


@router.get("/knowledge/search", response_model=list[KnowledgeNodeRead])
def knowledge_search(
    query: str = Query(...),
    node_type: str | None = Query(default=None),
    min_confidence: float = Query(default=0.0),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return KnowledgeRetrievalService(db).search(
        current_user.organization_id, query, node_type=node_type, min_confidence=min_confidence
    )


@router.get("/knowledge/stale", response_model=list[KnowledgeNodeRead])
def knowledge_stale(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Knowledge nodes that have not been refreshed recently (re-ingest candidates)."""
    return KnowledgeRetrievalService(db).stale_nodes(current_user.organization_id)


@router.get("/knowledge/graph", response_model=KnowledgeNeighbor)
def knowledge_graph(
    node_id: uuid.UUID = Query(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return KnowledgeRetrievalService(db).neighborhood(node_id, current_user.organization_id)


@router.get("/knowledge/nodes/{node_id}", response_model=KnowledgeNodeRead)
def knowledge_node(
    node_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return KnowledgeRetrievalService(db).get_node(node_id, current_user.organization_id)


@router.post("/knowledge/ingest", response_model=KnowledgeIngestResult)
def knowledge_ingest(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Read-only ingestion: rebuild the knowledge graph from current CodeDNA data."""
    return KnowledgeIngestionService(db).ingest(current_user.organization_id)


# -- engineering intelligence (Phase 12.2) -----------------------------------


@router.get("/engineering/overview", response_model=EngineeringOverview)
def engineering_overview(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Component map, dependency counts, top dependencies, and orphans."""
    return EngineeringIntelligenceService(db).overview(current_user.organization_id)


@router.get("/engineering/impact", response_model=ImpactResult)
def engineering_impact(
    query: str = Query(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Components and likely-affected files connected to a change/topic."""
    return EngineeringIntelligenceService(db).impact(current_user.organization_id, query)


@router.get("/engineering/dependencies", response_model=DependencyResult)
def engineering_dependencies(
    node_id: uuid.UUID = Query(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Dependencies and dependents of a component."""
    return EngineeringIntelligenceService(db).dependencies(current_user.organization_id, node_id)


@router.get("/engineering/architecture", response_model=ArchitectureReview)
def engineering_architecture(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Architecture review: hotspots, orphans, stale knowledge, integration coupling."""
    return EngineeringIntelligenceService(db).architecture_review(current_user.organization_id)


# -- debug intelligence (Phase 12.3) -----------------------------------------


@router.post("/debug/diagnose", response_model=DebugDiagnosisRead)
def debug_diagnose(
    payload: DiagnoseRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Read-only root-cause analysis of a failure log. No code changes are made."""
    return DebugIntelligenceService(db).diagnose(
        organization_id=current_user.organization_id,
        logs=payload.logs,
        source=payload.source or "manual",
        source_ref=payload.source_ref,
    )


@router.get("/debug/failures", response_model=list[DebugFailureRead])
def debug_failures(
    failure_type: str | None = Query(default=None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return DebugIntelligenceService(db).list_failures(current_user.organization_id, failure_type=failure_type)


@router.get("/debug/patterns", response_model=list[DebugPattern])
def debug_patterns(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Recurring failure patterns grouped by normalized signature."""
    return DebugIntelligenceService(db).patterns(current_user.organization_id)


@router.get("/debug/failures/{failure_id}", response_model=DebugFailureDetail)
def debug_failure_detail(
    failure_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return DebugIntelligenceService(db).get_failure(failure_id, current_user.organization_id)
