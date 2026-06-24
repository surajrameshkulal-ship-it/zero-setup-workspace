from __future__ import annotations
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AuthenticationError
from app.models.github import GitHubInstallation
from app.models.repository import Repository
from app.models.scan import PullRequestScan, ScanStatus
from app.schemas.github import GitHubWebhookResponse
from app.services.audit_service import AuditService
from app.utils.webhooks import verify_github_signature

logger = logging.getLogger(__name__)


PR_ACTIONS_TO_SCAN = {"opened", "reopened", "synchronize", "ready_for_review"}


class GitHubWebhookService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def verify(self, body: bytes, signature: str | None) -> None:
        if not verify_github_signature(body, signature, settings.github_webhook_secret):
            raise AuthenticationError("Invalid GitHub webhook signature")

    def handle(self, *, event: str, payload: dict) -> GitHubWebhookResponse:
        if event == "ping":
            return GitHubWebhookResponse(accepted=True, message="GitHub webhook ping received")
        if event == "installation":
            return self._handle_installation_event(payload)
        if event == "pull_request":
            return self._handle_pull_request_event(payload)
        return GitHubWebhookResponse(accepted=False, action=event, message="Webhook event ignored")

    def _handle_installation_event(self, payload: dict) -> GitHubWebhookResponse:
        installation_payload = payload.get("installation") or {}
        installation_id = installation_payload.get("id")
        if not installation_id:
            return GitHubWebhookResponse(accepted=False, action="installation", message="Installation id missing")

        installation = self.db.scalar(
            select(GitHubInstallation).where(GitHubInstallation.installation_id == int(installation_id))
        )
        if installation:
            account = installation_payload.get("account") or {}
            installation.account_login = account.get("login") or installation.account_login
            installation.account_type = account.get("type") or installation.account_type
            installation.permissions = installation_payload.get("permissions") or installation.permissions
            AuditService(self.db).log(
                organization_id=installation.organization_id,
                action=f"github_installation.{payload.get('action', 'updated')}",
                target_type="github_installation",
                target_id=str(installation.id),
                metadata={"installation_id": installation.installation_id},
            )
            self.db.commit()
        return GitHubWebhookResponse(accepted=True, action="installation", message="Installation event processed")

    def _handle_pull_request_event(self, payload: dict) -> GitHubWebhookResponse:
        action = payload.get("action")
        if action not in PR_ACTIONS_TO_SCAN:
            return GitHubWebhookResponse(accepted=False, action=action, message="Pull request action ignored")

        installation_id = (payload.get("installation") or {}).get("id")
        if not installation_id:
            return GitHubWebhookResponse(accepted=False, action=action, message="Installation id missing")

        installation = self.db.scalar(
            select(GitHubInstallation).where(GitHubInstallation.installation_id == int(installation_id))
        )
        if not installation:
            logger.info("webhook_installation_unregistered", extra={"installation_id": installation_id})
            return GitHubWebhookResponse(
                accepted=False,
                action=action,
                message="GitHub installation is not registered to an organization",
            )

        repository_payload = payload.get("repository") or {}
        pull_request = payload.get("pull_request") or {}
        repository = self._upsert_repository(installation, repository_payload)
        scan = PullRequestScan(
            organization_id=installation.organization_id,
            repository_id=repository.id,
            github_pr_number=int(pull_request["number"]),
            github_pr_url=pull_request.get("html_url"),
            title=pull_request.get("title"),
            head_sha=(pull_request.get("head") or {}).get("sha"),
            base_sha=(pull_request.get("base") or {}).get("sha"),
            status=ScanStatus.QUEUED,
            trigger="webhook",
        )
        self.db.add(scan)
        self.db.flush()
        AuditService(self.db).log(
            organization_id=installation.organization_id,
            action="scan.queued.webhook",
            target_type="pull_request_scan",
            target_id=str(scan.id),
            metadata={
                "repository": repository.full_name,
                "pr_number": scan.github_pr_number,
                "action": action,
                "sender": (payload.get("sender") or {}).get("login"),
            },
        )
        self.db.commit()

        from app.workers.tasks import run_pr_scan

        run_pr_scan.delay(str(scan.id))
        return GitHubWebhookResponse(accepted=True, action=action, scan_id=scan.id, message="PR scan queued")

    def _upsert_repository(self, installation: GitHubInstallation, payload: dict) -> Repository:
        owner = (payload.get("owner") or {}).get("login")
        name = payload.get("name")
        full_name = payload.get("full_name") or f"{owner}/{name}"
        repository = self.db.scalar(
            select(Repository).where(
                Repository.organization_id == installation.organization_id,
                Repository.github_repository_id == int(payload["id"]),
            )
        )
        if repository:
            repository.github_installation_id = installation.id
            repository.owner = owner
            repository.name = name
            repository.full_name = full_name
            repository.default_branch = payload.get("default_branch") or repository.default_branch
            repository.is_active = True
            return repository

        repository = Repository(
            organization_id=installation.organization_id,
            github_installation_id=installation.id,
            github_repository_id=int(payload["id"]),
            owner=owner,
            name=name,
            full_name=full_name,
            default_branch=payload.get("default_branch") or "main",
        )
        self.db.add(repository)
        self.db.flush()
        return repository

