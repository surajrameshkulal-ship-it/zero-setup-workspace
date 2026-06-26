from __future__ import annotations
import uuid
from datetime import datetime

from app.schemas.common import ORMModel


class WorkspaceLaunchRead(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    repository_id: uuid.UUID
    repository_full_name: str | None
    status: str
    runtime: str | None
    image: str | None
    start_command: str | None
    container_id: str | None
    published_url: str | None
    port_mappings: list
    health_status: str | None
    health_detail: str | None
    logs_tail: list
    resource_limits: dict
    ttl_seconds: int
    started_at: str | None
    expires_at: str | None
    stopped_at: str | None
    safety: dict
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime
