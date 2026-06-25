from __future__ import annotations
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.models.repository import Repository
from app.models.repository_dna import RepositoryDNA
from app.models.scan import PullRequestScan
from app.models.user import User
from app.schemas.repository import RepositoryConnectRequest, RepositoryRead, RepositoryUpdate
from app.schemas.repository_dna import RepositoryDNARead
from app.schemas.scan import ManualScanRequest, ScanListItem, ScanQueuedResponse
from app.services.repository_dna_service import RepositoryDNAService
from app.services.repository_service import RepositoryService
from app.services.scan_service import PullRequestScanService


router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.get("", response_model=list[RepositoryRead])
def list_repositories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Repository]:
    return RepositoryService(db).list_for_org(current_user.organization_id)


@router.post("", response_model=RepositoryRead, status_code=201)
def connect_repository(
    payload: RepositoryConnectRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Repository:
    return RepositoryService(db).connect(current_user.organization_id, current_user.id, payload)


@router.get("/{repository_id}", response_model=RepositoryRead)
def get_repository(
    repository_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Repository:
    return RepositoryService(db).get_for_org(repository_id, current_user.organization_id)


@router.patch("/{repository_id}", response_model=RepositoryRead)
def update_repository(
    repository_id: uuid.UUID,
    payload: RepositoryUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Repository:
    service = RepositoryService(db)
    repository = service.get_for_org(repository_id, current_user.organization_id)
    return service.update(repository, current_user.id, payload)


@router.get("/{repository_id}/scans", response_model=list[ScanListItem])
def list_repository_scans(
    repository_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PullRequestScan]:
    RepositoryService(db).get_for_org(repository_id, current_user.organization_id)
    return PullRequestScanService(db).list_for_org(
        current_user.organization_id,
        repository_id=repository_id,
        limit=limit,
    )


@router.post("/{repository_id}/dna", response_model=RepositoryDNARead)
def generate_repository_dna(
    repository_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RepositoryDNA:
    """Generate a read-only DNA fingerprint for a repository. No cloning or Git writes."""
    return RepositoryDNAService(db).generate(
        repository_id=repository_id,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
    )


@router.get("/{repository_id}/dna", response_model=RepositoryDNARead)
def get_repository_dna(
    repository_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RepositoryDNA:
    return RepositoryDNAService(db).get_for_repository(repository_id, current_user.organization_id)


@router.post("/{repository_id}/scans", response_model=ScanQueuedResponse, status_code=202)
def queue_manual_scan(
    repository_id: uuid.UUID,
    payload: ManualScanRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ScanQueuedResponse:
    service = RepositoryService(db)
    repository = service.get_for_org(repository_id, current_user.organization_id)
    scan: PullRequestScan = service.create_manual_scan(repository, current_user.id, payload)

    from app.workers.tasks import run_pr_scan

    run_pr_scan.delay(str(scan.id))
    return ScanQueuedResponse(scan_id=scan.id, status=scan.status)
