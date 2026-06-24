from __future__ import annotations
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.database import get_db
from app.models.setting import AdminSetting
from app.models.user import User
from app.schemas.admin import AdminSettingRead, AdminSettingUpsert
from app.services.settings_service import SettingsService


router = APIRouter(prefix="/admin/settings", tags=["admin"])


@router.get("", response_model=list[AdminSettingRead])
def list_settings(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AdminSetting]:
    return SettingsService(db).list_settings(current_user.organization_id)


@router.put("", response_model=AdminSettingRead)
def upsert_setting(
    payload: AdminSettingUpsert,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminSetting:
    return SettingsService(db).upsert(current_user.organization_id, current_user.id, payload)

