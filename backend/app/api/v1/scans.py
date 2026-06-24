from __future__ import annotations
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.scan import RiskLevel, ScanStatus
from app.models.scan import PullRequestScan
from app.models.user import User
from app.schemas.scan import ScanDetail, ScanListItem
from app.services.scan_service import PullRequestScanService


router = APIRouter(prefix="/scans", tags=["scans"])


@router.get("", response_model=list[ScanListItem])
def list_scans(
    repository_id: uuid.UUID | None = Query(default=None),
    status: ScanStatus | None = Query(default=None),
    risk_level: RiskLevel | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PullRequestScan]:
    return PullRequestScanService(db).list_for_org(
        current_user.organization_id,
        repository_id=repository_id,
        status=status,
        risk_level=risk_level,
        limit=limit,
    )


@router.get("/{scan_id}", response_model=ScanDetail)
def get_scan(
    scan_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PullRequestScan:
    return PullRequestScanService(db).get_for_org(scan_id, current_user.organization_id)
