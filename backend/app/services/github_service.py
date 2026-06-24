from __future__ import annotations
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.models.github import GitHubInstallation
from app.schemas.github import GitHubInstallationRegisterRequest
from app.services.audit_service import AuditService


class GitHubService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def install_url(self) -> str:
        if not settings.github_app_slug:
            raise AppError("GITHUB_APP_SLUG is not configured", code="github_app_not_configured")
        return f"https://github.com/apps/{settings.github_app_slug}/installations/new"

    def list_installations(self, organization_id: uuid.UUID) -> list[GitHubInstallation]:
        return list(
            self.db.scalars(
                select(GitHubInstallation)
                .where(GitHubInstallation.organization_id == organization_id)
                .order_by(GitHubInstallation.account_login.asc())
            )
        )

    def register_installation(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        payload: GitHubInstallationRegisterRequest,
    ) -> GitHubInstallation:
        installation = self.db.scalar(
            select(GitHubInstallation).where(GitHubInstallation.installation_id == payload.installation_id)
        )
        if installation and installation.organization_id != organization_id:
            raise AppError("This GitHub installation is already registered to another organization", code="installation_taken")

        if installation:
            installation.account_login = payload.account_login
            installation.account_type = payload.account_type
            installation.permissions = payload.permissions
            action = "github_installation.updated"
        else:
            installation = GitHubInstallation(
                organization_id=organization_id,
                installation_id=payload.installation_id,
                account_login=payload.account_login,
                account_type=payload.account_type,
                permissions=payload.permissions,
            )
            self.db.add(installation)
            action = "github_installation.registered"

        self.db.flush()
        AuditService(self.db).log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type="github_installation",
            target_id=str(installation.id),
            metadata={"installation_id": payload.installation_id, "account_login": payload.account_login},
        )
        self.db.commit()
        self.db.refresh(installation)
        return installation

