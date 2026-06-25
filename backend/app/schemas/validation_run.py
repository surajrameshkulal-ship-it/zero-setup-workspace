from __future__ import annotations
import uuid
from datetime import datetime

from app.schemas.common import ORMModel


class ValidationRunRead(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    engineering_request_id: uuid.UUID
    repository_id: uuid.UUID | None
    draft_pull_request_id: uuid.UUID | None
    status: str
    attempts: int
    max_attempts: int
    checks: list
    auto_fixes_applied: list
    report: dict
    created_at: datetime
    updated_at: datetime
