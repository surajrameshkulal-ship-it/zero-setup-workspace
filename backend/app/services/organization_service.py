from __future__ import annotations
import uuid

from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.schemas.organization import OrganizationUpdate
from app.services.audit_service import AuditService


class OrganizationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def update(self, organization: Organization, payload: OrganizationUpdate, actor_user_id: uuid.UUID) -> Organization:
        updates = payload.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(organization, field, value)

        AuditService(self.db).log(
            organization_id=organization.id,
            actor_user_id=actor_user_id,
            action="organization.updated",
            target_type="organization",
            target_id=str(organization.id),
            metadata=updates,
        )
        self.db.commit()
        self.db.refresh(organization)
        return organization
