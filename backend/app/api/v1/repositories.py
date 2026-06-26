from __future__ import annotations
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.models.environment_spec import EnvironmentSpec
from app.models.repository import Repository
from app.models.repository_dna import RepositoryDNA
from app.models.scan import PullRequestScan
from app.models.setup_intent import SetupIntent
from app.models.user import User
from app.models.workspace_blueprint import WorkspaceBlueprint
from app.models.workspace_provision_plan import WorkspaceProvisionPlan
from app.schemas.environment_spec import EnvironmentSpecRead
from app.schemas.repository import RepositoryConnectRequest, RepositoryRead, RepositoryUpdate
from app.schemas.repository_dna import RepositoryDNARead
from app.schemas.scan import ManualScanRequest, ScanListItem, ScanQueuedResponse
from app.schemas.setup_intent import SetupIntentRead
from app.schemas.workspace_blueprint import WorkspaceBlueprintRead
from app.schemas.workspace_provision_plan import WorkspaceProvisionPlanRead
from app.services.repository_dna_service import RepositoryDNAService
from app.services.repository_service import RepositoryService
from app.services.scan_service import PullRequestScanService
from app.services.workspace.environment_spec_generator import EnvironmentSpecGenerator
from app.services.workspace.setup_intent_reader import SetupIntentReader
from app.services.workspace.workspace_builder import WorkspaceBuilder
from app.services.workspace.workspace_provisioner import WorkspaceProvisioner


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


@router.get("/{repository_id}/setup-intent", response_model=SetupIntentRead)
def get_setup_intent(
    repository_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SetupIntent:
    return SetupIntentReader(db).get_for_repository(repository_id, current_user.organization_id)


@router.post("/{repository_id}/setup-intent", response_model=SetupIntentRead)
def generate_setup_intent(
    repository_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SetupIntent:
    """Read-only analysis of repository manifests to infer build/run setup."""
    return SetupIntentReader(db).generate(
        repository_id=repository_id,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
    )


@router.get("/{repository_id}/environment-spec", response_model=EnvironmentSpecRead)
def get_environment_spec(
    repository_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EnvironmentSpec:
    return EnvironmentSpecGenerator(db).get_for_repository(repository_id, current_user.organization_id)


@router.post("/{repository_id}/environment-spec", response_model=EnvironmentSpecRead)
def generate_environment_spec(
    repository_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EnvironmentSpec:
    """Convert the repository's setup intent into a normalized environment spec.

    Specification only — never launches, executes, or installs anything.
    """
    return EnvironmentSpecGenerator(db).generate(
        repository_id=repository_id,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
    )


@router.get("/{repository_id}/workspace-blueprint", response_model=WorkspaceBlueprintRead)
def get_workspace_blueprint(
    repository_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceBlueprint:
    return WorkspaceBuilder(db).get_for_repository(repository_id, current_user.organization_id)


@router.post("/{repository_id}/workspace-blueprint", response_model=WorkspaceBlueprintRead)
def generate_workspace_blueprint(
    repository_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceBlueprint:
    """Convert the environment spec into a reproducible workspace blueprint.

    Planning/generation only — never launches, executes, installs, or modifies.
    """
    return WorkspaceBuilder(db).generate(
        repository_id=repository_id,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
    )


@router.get("/{repository_id}/workspace-provision", response_model=WorkspaceProvisionPlanRead)
def get_workspace_provision(
    repository_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceProvisionPlan:
    return WorkspaceProvisioner(db).get_for_repository(repository_id, current_user.organization_id)


@router.post("/{repository_id}/workspace-provision", response_model=WorkspaceProvisionPlanRead)
def generate_workspace_provision(
    repository_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceProvisionPlan:
    """Prepare a runnable workspace plan from the workspace blueprint.

    Preparation only — never starts Docker, runs compose, executes code,
    starts services, installs dependencies, deploys, or modifies the repository.
    """
    return WorkspaceProvisioner(db).generate(
        repository_id=repository_id,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
    )


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
