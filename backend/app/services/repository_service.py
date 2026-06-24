from __future__ import annotations
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.github import GitHubInstallation
from app.models.repository import Repository
from app.models.scan import PullRequestScan, ScanStatus
from app.schemas.repository import RepositoryConnectRequest, RepositoryUpdate
from app.schemas.scan import ManualScanRequest
from app.services.audit_service import AuditService


class RepositoryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_org(self, organization_id: uuid.UUID) -> list[Repository]:
        return list(
            self.db.scalars(
                select(Repository)
                .where(Repository.organization_id == organization_id)
                .order_by(Repository.full_name.asc())
            )
        )

    def get_for_org(self, repository_id: uuid.UUID, organization_id: uuid.UUID) -> Repository:
        repository = self.db.scalar(
            select(Repository).where(
                Repository.id == repository_id,
                Repository.organization_id == organization_id,
            )
        )
        if not repository:
            raise NotFoundError("Repository not found")
        return repository

    def connect(
        self,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        payload: RepositoryConnectRequest,
    ) -> Repository:
        installation = self.db.scalar(
            select(GitHubInstallation).where(
                GitHubInstallation.organization_id == organization_id,
                GitHubInstallation.installation_id == payload.installation_id,
            )
        )
        if not installation:
            raise NotFoundError("GitHub installation not registered for this organization")

        full_name = f"{payload.owner}/{payload.name}"
        repository = self.db.scalar(
            select(Repository).where(
                Repository.organization_id == organization_id,
                Repository.github_repository_id == payload.github_repository_id,
            )
        )
        if repository:
            repository.github_installation_id = installation.id
            repository.owner = payload.owner
            repository.name = payload.name
            repository.full_name = full_name
            repository.default_branch = payload.default_branch
            repository.is_active = True
            action = "repository.updated"
        else:
            repository = Repository(
                organization_id=organization_id,
                github_installation_id=installation.id,
                github_repository_id=payload.github_repository_id,
                owner=payload.owner,
                name=payload.name,
                full_name=full_name,
                default_branch=payload.default_branch,
            )
            self.db.add(repository)
            action = "repository.connected"

        self.db.flush()
        AuditService(self.db).log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type="repository",
            target_id=str(repository.id),
            metadata={"full_name": full_name},
        )
        self.db.commit()
        self.db.refresh(repository)
        return repository

    def update(
        self,
        repository: Repository,
        actor_user_id: uuid.UUID,
        payload: RepositoryUpdate,
    ) -> Repository:
        updates = payload.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(repository, field, value)
        AuditService(self.db).log(
            organization_id=repository.organization_id,
            actor_user_id=actor_user_id,
            action="repository.updated",
            target_type="repository",
            target_id=str(repository.id),
            metadata=updates,
        )
        self.db.commit()
        self.db.refresh(repository)
        return repository

    def create_manual_scan(
        self,
        repository: Repository,
        actor_user_id: uuid.UUID,
        payload: ManualScanRequest,
    ) -> PullRequestScan:
        scan = PullRequestScan(
            organization_id=repository.organization_id,
            repository_id=repository.id,
            github_pr_number=payload.github_pr_number,
            github_pr_url=payload.github_pr_url,
            title=payload.title,
            head_sha=payload.head_sha,
            base_sha=payload.base_sha,
            status=ScanStatus.QUEUED,
            trigger="manual",
        )
        self.db.add(scan)
        self.db.flush()
        AuditService(self.db).log(
            organization_id=repository.organization_id,
            actor_user_id=actor_user_id,
            action="scan.queued.manual",
            target_type="pull_request_scan",
            target_id=str(scan.id),
            metadata={"repository": repository.full_name, "pr_number": payload.github_pr_number},
        )
        self.db.commit()
        self.db.refresh(scan)
        return scan

