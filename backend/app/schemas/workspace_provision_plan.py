from __future__ import annotations
import uuid
from datetime import datetime

from app.schemas.common import ORMModel


class WorkspaceProvisionPlanRead(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    repository_id: uuid.UUID
    repository_full_name: str | None
    language: str | None
    runtime: str | None
    runtime_version: str | None
    package_manager: str | None
    framework: str | None
    workspace_directory: dict
    environment_preparation: dict
    container_preparation: dict
    dependency_plan: list
    startup_plan: list
    validation: list
    readiness_score: int
    recommendations: list
    warnings: list
    safety: dict
    created_at: datetime
    updated_at: datetime
