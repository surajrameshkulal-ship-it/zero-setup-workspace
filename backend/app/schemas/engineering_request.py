from __future__ import annotations
import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.engineering_request import RequestPriority, RequestStatus, RequestType
from app.models.scan import RiskLevel
from app.schemas.common import ORMModel


class EngineeringRequestCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=512)
    description: str = Field(..., min_length=1)
    request_type: RequestType = RequestType.OTHER
    priority: RequestPriority = RequestPriority.MEDIUM
    repository_id: uuid.UUID | None = None


class EngineeringRequestListItem(ORMModel):
    id: uuid.UUID
    repository_id: uuid.UUID | None
    repository_full_name: str | None
    title: str
    request_type: RequestType
    status: RequestStatus
    priority: RequestPriority
    risk_level: RiskLevel | None
    created_at: datetime
    updated_at: datetime


class EngineeringRequestDetail(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    repository_id: uuid.UUID | None
    repository_full_name: str | None
    created_by_user_id: uuid.UUID | None
    title: str
    description: str
    request_type: RequestType
    status: RequestStatus
    priority: RequestPriority
    ai_summary: str | None
    affected_files: list
    implementation_plan: list
    test_plan: list
    risk_level: RiskLevel | None
    safety_notes: dict
    created_at: datetime
    updated_at: datetime


class RejectPlanRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)
