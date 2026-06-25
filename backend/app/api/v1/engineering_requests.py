from __future__ import annotations
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.engineering_request import EngineeringRequest, RequestStatus, RequestType
from app.models.user import User
from app.models.code_generation import CodeGenerationPreview
from app.models.draft_pull_request import DraftPullRequest
from app.models.execution_plan import ExecutionPlan
from app.schemas.code_generation import CodeGenerationPreviewRead
from app.schemas.draft_pull_request import DraftPullRequestRead
from app.schemas.engineering_request import (
    EngineeringRequestCreate,
    EngineeringRequestDetail,
    EngineeringRequestListItem,
    RejectPlanRequest,
)
from app.schemas.execution_plan import ExecutionPlanRead
from app.services.agent.code_generation_service import CodeGenerationService
from app.services.agent.draft_pr_service import DraftPullRequestService
from app.services.engineering_request_service import EngineeringRequestService
from app.services.execution.execution_plan_service import ExecutionPlanService

router = APIRouter(prefix="/engineering-requests", tags=["engineering-requests"])


@router.post("", response_model=EngineeringRequestDetail, status_code=status.HTTP_201_CREATED)
def create_engineering_request(
    payload: EngineeringRequestCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EngineeringRequest:
    return EngineeringRequestService(db).create(
        organization_id=current_user.organization_id,
        created_by_user_id=current_user.id,
        payload=payload,
    )


@router.get("", response_model=list[EngineeringRequestListItem])
def list_engineering_requests(
    status: RequestStatus | None = Query(default=None),
    request_type: RequestType | None = Query(default=None),
    repository_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[EngineeringRequest]:
    return EngineeringRequestService(db).list_for_org(
        current_user.organization_id,
        status=status,
        request_type=request_type,
        repository_id=repository_id,
        limit=limit,
    )


@router.get("/{request_id}", response_model=EngineeringRequestDetail)
def get_engineering_request(
    request_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EngineeringRequest:
    return EngineeringRequestService(db).get_for_org(request_id, current_user.organization_id)


@router.post("/{request_id}/analyze", response_model=EngineeringRequestDetail)
def analyze_engineering_request(
    request_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EngineeringRequest:
    return EngineeringRequestService(db).analyze(
        request_id=request_id,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
    )


@router.post("/{request_id}/approve-plan", response_model=EngineeringRequestDetail)
def approve_engineering_request_plan(
    request_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EngineeringRequest:
    return EngineeringRequestService(db).approve_plan(
        request_id=request_id,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
    )


@router.post("/{request_id}/reject-plan", response_model=EngineeringRequestDetail)
def reject_engineering_request_plan(
    request_id: uuid.UUID,
    payload: RejectPlanRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EngineeringRequest:
    return EngineeringRequestService(db).reject_plan(
        request_id=request_id,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        reason=payload.reason if payload else None,
    )


@router.post("/{request_id}/execution-plan", response_model=ExecutionPlanRead)
def generate_execution_plan(
    request_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExecutionPlan:
    """Generate planning-only execution metadata for an approved request.

    Produces no source code and performs no GitHub action.
    """
    return ExecutionPlanService(db).generate(
        engineering_request_id=request_id,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
    )


@router.get("/{request_id}/execution-plan", response_model=ExecutionPlanRead)
def get_execution_plan(
    request_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExecutionPlan:
    return ExecutionPlanService(db).get_for_request(request_id, current_user.organization_id)


@router.post("/{request_id}/code-generation", response_model=CodeGenerationPreviewRead)
def generate_code_preview(
    request_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CodeGenerationPreview:
    """Produce an implementation PREVIEW only. No files, commits, branches, PRs, or deploys."""
    return CodeGenerationService(db).generate(
        engineering_request_id=request_id,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
    )


@router.get("/{request_id}/code-generation", response_model=CodeGenerationPreviewRead)
def get_code_preview(
    request_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CodeGenerationPreview:
    return CodeGenerationService(db).get_for_request(request_id, current_user.organization_id)


@router.post("/{request_id}/draft-pr", response_model=DraftPullRequestRead)
def prepare_draft_pull_request(
    request_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DraftPullRequest:
    """Prepare draft PR metadata only. Never pushes, opens a PR, merges, or deploys."""
    return DraftPullRequestService(db).generate(
        engineering_request_id=request_id,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
    )


@router.get("/{request_id}/draft-pr", response_model=DraftPullRequestRead)
def get_draft_pull_request(
    request_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DraftPullRequest:
    return DraftPullRequestService(db).get_for_request(request_id, current_user.organization_id)
