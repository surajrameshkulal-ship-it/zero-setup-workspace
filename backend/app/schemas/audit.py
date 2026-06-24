from __future__ import annotations
import uuid
from datetime import datetime

from app.schemas.common import ORMModel


class AuditLogRead(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action: str
    target_type: str | None
    target_id: str | None
    event_metadata: dict
    ip_address: str | None
    user_agent: str | None
    created_at: datetime

