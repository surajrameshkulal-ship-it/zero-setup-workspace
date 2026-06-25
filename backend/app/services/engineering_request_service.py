from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import AppError, NotFoundError
from app.models.engineering_request import (
    EngineeringRequest,
    RequestPriority,
    RequestStatus,
    RequestType,
)
from app.models.repository import Repository
from app.models.scan import PullRequestScan
from app.schemas.engineering_request import EngineeringRequestCreate
from app.services.audit_service import AuditService
from app.services.engineering_planning_service import EngineeringPlanningService

logger = logging.getLogger(__name__)

# Statuses from which (re)analysis is permitted.
ANALYZABLE_STATUSES = {
    RequestStatus.SUBMITTED,
    RequestStatus.PLAN_READY,
    RequestStatus.REJECTED,
    RequestStatus.FAILED,
}


class EngineeringRequestService:
    def __init__(self, db: Session, *, planning_service: EngineeringPlanningService | None = None) -> None:
        self.db = db
        self.audit = AuditService(db)
        self._planning_service = planning_service

    @property
    def planning_service(self) -> EngineeringPlanningService:
        # Lazily construct so importing the service never requires AI config.
        if self._planning_service is None:
            self._planning_service = EngineeringPlanningService()
        return self._planning_service

    # -- queries ---------------------------------------------------------------

    def list_for_org(
        self,
        organization_id: uuid.UUID,
        *,
        status: RequestStatus | None = None,
        request_type: RequestType | None = None,
        repository_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[EngineeringRequest]:
        query = (
            select(EngineeringRequest)
            .options(joinedload(EngineeringRequest.repository))
            .where(EngineeringRequest.organization_id == organization_id)
            .order_by(EngineeringRequest.created_at.desc())
            .limit(limit)
        )
        if status:
            query = query.where(EngineeringRequest.status == status)
        if request_type:
            query = query.where(EngineeringRequest.request_type == request_type)
        if repository_id:
            query = query.where(EngineeringRequest.repository_id == repository_id)
        return list(self.db.scalars(query).all())

    def get_for_org(self, request_id: uuid.UUID, organization_id: uuid.UUID) -> EngineeringRequest:
        request = self.db.scalar(
            select(EngineeringRequest)
            .options(joinedload(EngineeringRequest.repository))
            .where(
                EngineeringRequest.id == request_id,
                EngineeringRequest.organization_id == organization_id,
            )
        )
        if not request:
            raise NotFoundError("Engineering request not found")
        return request

    # -- commands --------------------------------------------------------------

    def create(
        self,
        *,
        organization_id: uuid.UUID,
        created_by_user_id: uuid.UUID | None,
        payload: EngineeringRequestCreate,
    ) -> EngineeringRequest:
        if payload.repository_id is not None:
            self._require_repository(payload.repository_id, organization_id)

        request = EngineeringRequest(
            organization_id=organization_id,
            repository_id=payload.repository_id,
            created_by_user_id=created_by_user_id,
            title=payload.title,
            description=payload.description,
            request_type=payload.request_type,
            priority=payload.priority,
            status=RequestStatus.SUBMITTED,
            affected_files=[],
            implementation_plan=[],
            test_plan=[],
            safety_notes={},
        )
        self.db.add(request)
        self.db.flush()
        self.audit.log(
            organization_id=organization_id,
            actor_user_id=created_by_user_id,
            action="engineering_request_created",
            target_type="engineering_request",
            target_id=str(request.id),
            metadata={
                "request_type": request.request_type.value,
                "priority": request.priority.value,
            },
        )
        self.db.commit()
        self.db.refresh(request)
        return request

    def analyze(
        self,
        *,
        request_id: uuid.UUID,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
    ) -> EngineeringRequest:
        request = self.get_for_org(request_id, organization_id)
        if request.status not in ANALYZABLE_STATUSES:
            raise AppError(f"Cannot analyze a request in status '{request.status.value}'")

        request.status = RequestStatus.ANALYZING
        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="engineering_request_analysis_started",
            target_type="engineering_request",
            target_id=str(request.id),
            metadata={"request_type": request.request_type.value},
        )
        self.db.flush()

        recent_scans = self._recent_scans(organization_id, request.repository_id)
        plan = self.planning_service.generate_plan(
            request=request,
            repository=request.repository,
            recent_scans=recent_scans,
        )

        request.ai_summary = plan["ai_summary"]
        request.affected_files = plan["affected_files"]
        request.implementation_plan = plan["implementation_plan"]
        request.test_plan = plan["test_plan"]
        request.risk_level = plan["risk_level"]
        request.safety_notes = plan["safety_notes"]
        request.status = RequestStatus.PLAN_READY

        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="engineering_request_plan_ready",
            target_type="engineering_request",
            target_id=str(request.id),
            metadata={
                "risk_level": request.risk_level.value if request.risk_level else None,
                "affected_file_count": len(request.affected_files),
            },
        )
        self.db.commit()
        self.db.refresh(request)
        return request

    def approve_plan(
        self,
        *,
        request_id: uuid.UUID,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
    ) -> EngineeringRequest:
        request = self.get_for_org(request_id, organization_id)
        if request.status != RequestStatus.PLAN_READY:
            raise AppError("Only a request with a ready plan can be approved")

        request.status = RequestStatus.APPROVED
        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="engineering_request_approved",
            target_type="engineering_request",
            target_id=str(request.id),
            metadata={"risk_level": request.risk_level.value if request.risk_level else None},
        )
        self.db.commit()
        self.db.refresh(request)
        return request

    def reject_plan(
        self,
        *,
        request_id: uuid.UUID,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        reason: str | None = None,
    ) -> EngineeringRequest:
        request = self.get_for_org(request_id, organization_id)
        if request.status != RequestStatus.PLAN_READY:
            raise AppError("Only a request with a ready plan can be rejected")

        request.status = RequestStatus.REJECTED
        if reason:
            notes = dict(request.safety_notes or {})
            notes["rejection_reason"] = reason
            request.safety_notes = notes
        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="engineering_request_rejected",
            target_type="engineering_request",
            target_id=str(request.id),
            metadata={"reason": reason},
        )
        self.db.commit()
        self.db.refresh(request)
        return request

    # -- helpers ---------------------------------------------------------------

    def _require_repository(self, repository_id: uuid.UUID, organization_id: uuid.UUID) -> Repository:
        repository = self.db.scalar(
            select(Repository).where(
                Repository.id == repository_id,
                Repository.organization_id == organization_id,
            )
        )
        if not repository:
            raise NotFoundError("Repository not found")
        return repository

    def _recent_scans(
        self, organization_id: uuid.UUID, repository_id: uuid.UUID | None
    ) -> list[PullRequestScan]:
        query = (
            select(PullRequestScan)
            .where(PullRequestScan.organization_id == organization_id)
            .order_by(PullRequestScan.created_at.desc())
            .limit(5)
        )
        if repository_id:
            query = query.where(PullRequestScan.repository_id == repository_id)
        return list(self.db.scalars(query).all())
