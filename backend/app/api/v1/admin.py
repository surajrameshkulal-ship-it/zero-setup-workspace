from __future__ import annotations
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.database import get_db
from app.models.repository import Repository
from app.models.setting import AdminSetting
from app.models.user import User
from app.schemas.admin import AdminSettingRead, AdminSettingUpsert, DeadLetterScanItem
from app.schemas.health import QueueMetricsRead
from app.services.audit_service import AuditService
from app.services.dead_letter_service import DeadLetterScanService
from app.services.queue_metrics_service import QueueMetricsService
from app.services.settings_service import SettingsService


router = APIRouter(tags=["admin"])


def get_dead_letter_scan_service() -> DeadLetterScanService:
    return DeadLetterScanService()


def get_queue_metrics_service() -> QueueMetricsService:
    return QueueMetricsService()


@router.get("/admin/settings", response_model=list[AdminSettingRead])
def list_settings(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AdminSetting]:
    AuditService(db).log(
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        action="admin.settings.listed",
        target_type="admin_setting",
        metadata={},
    )
    db.commit()
    return SettingsService(db).list_settings(current_user.organization_id)


@router.put("/admin/settings", response_model=AdminSettingRead)
def upsert_setting(
    payload: AdminSettingUpsert,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminSetting:
    return SettingsService(db).upsert(current_user.organization_id, current_user.id, payload)


@router.get("/admin/dead-letter-scans", response_model=list[DeadLetterScanItem])
def list_dead_letter_scans(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
    dead_letters: DeadLetterScanService = Depends(get_dead_letter_scan_service),
) -> list[dict]:
    AuditService(db).log(
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        action="admin.dead_letter_scans.viewed",
        target_type="dead_letter_scan",
        metadata={"limit": limit},
    )
    db.commit()
    repository_ids = set(
        db.scalars(select(Repository.id).where(Repository.organization_id == current_user.organization_id))
    )
    return dead_letters.list_recent(limit=limit, repository_ids=repository_ids)


@router.get("/admin/queue-metrics", response_model=QueueMetricsRead)
def queue_metrics(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
    metrics_service: QueueMetricsService = Depends(get_queue_metrics_service),
) -> dict:
    AuditService(db).log(
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        action="admin.queue_metrics.viewed",
        target_type="queue_metrics",
        metadata={},
    )
    db.commit()
    return metrics_service.get_metrics()
