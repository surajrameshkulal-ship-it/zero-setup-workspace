from __future__ import annotations
import uuid
from datetime import datetime

from app.schemas.common import ORMModel


class CodeGenerationPreviewRead(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    engineering_request_id: uuid.UUID
    repository_id: uuid.UUID | None
    summary: str | None
    affected_files: list
    diff_preview: str | None
    implementation_tasks: list
    estimated_changes: dict
    documentation_updates: list
    tests_to_create: list
    ai_available: bool
    created_at: datetime
    updated_at: datetime
