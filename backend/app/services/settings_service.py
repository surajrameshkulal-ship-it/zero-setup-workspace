from __future__ import annotations
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.setting import AdminSetting
from app.schemas.admin import AdminSettingUpsert
from app.services.audit_service import AuditService


class SettingsService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_settings(self, organization_id: uuid.UUID) -> list[AdminSetting]:
        return list(self.db.scalars(select(AdminSetting).where(AdminSetting.organization_id == organization_id)))

    def upsert(self, organization_id: uuid.UUID, actor_user_id: uuid.UUID, payload: AdminSettingUpsert) -> AdminSetting:
        setting = self.db.scalar(
            select(AdminSetting).where(
                AdminSetting.organization_id == organization_id,
                AdminSetting.key == payload.key,
            )
        )
        if setting:
            setting.value = payload.value
            action = "settings.updated"
        else:
            setting = AdminSetting(organization_id=organization_id, key=payload.key, value=payload.value)
            self.db.add(setting)
            action = "settings.created"

        self.db.flush()
        AuditService(self.db).log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type="admin_setting",
            target_id=str(setting.id),
            metadata={"key": payload.key},
        )
        self.db.commit()
        self.db.refresh(setting)
        return setting

