from __future__ import annotations
import uuid
from datetime import datetime

from app.models.execution_plan import ExecutionSafetyStatus
from app.schemas.common import ORMModel


class ExecutionPlanRead(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    engineering_request_id: uuid.UUID
    repository_id: uuid.UUID | None
    tasks: list
    estimated_files: list
    dependency_analysis: dict
    complexity: str
    estimated_duration: str | None
    rollback_strategy: list
    validation_checklist: list
    repository_context: dict
    safety_status: ExecutionSafetyStatus
    safety_findings: list
    branch_name: str | None
    created_at: datetime
    updated_at: datetime
