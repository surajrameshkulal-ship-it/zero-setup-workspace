from __future__ import annotations
import logging
import uuid

from sqlalchemy.orm import Session

from app.models.audit import AuditLog

logger = logging.getLogger(__name__)


class AuditService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def log(
        self,
        *,
        organization_id: uuid.UUID,
        action: str,
        actor_user_id: uuid.UUID | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        metadata: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLog:
        event = AuditLog(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            event_metadata=metadata or {},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(event)
        if actor_user_id:
            logger.info(
                "admin_action_audit_logged",
                extra={
                    "organization_id": str(organization_id),
                    "actor_user_id": str(actor_user_id),
                    "audit_action": action,
                    "target_type": target_type,
                    "target_id": target_id,
                },
            )
        return event
