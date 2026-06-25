from __future__ import annotations
import hashlib
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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
            logger.warning("security_check_failed", extra={"security_check": "github_webhook_signature"})
            raise AuthenticationError("Invalid GitHub webhook signature")
        logger.info("security_check_passed", extra={"security_check": "github_webhook_signature"})

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
        repository_id = repository.id
        repository_full_name = repository.full_name
        pr_number = int(pull_request["number"])
        head_sha = (pull_request.get("head") or {}).get("sha")
        if not head_sha:
            return GitHubWebhookResponse(accepted=False, action=action, message="Pull request head SHA missing")

        idempotency_key = self._idempotency_key(
            installation_id=int(installation_id),
            repository_id=str(repository_id),
            pr_number=pr_number,
            head_sha=head_sha,
            event_action=str(action),
        )
        logger.info(
            "webhook_idempotency_key_generated",
            extra={
                "installation_id": int(installation_id),
                "repository_id": str(repository_id),
                "pr_number": pr_number,
                "head_sha": head_sha,
                "event_action": action,
                "idempotency_key": idempotency_key,
            },
        )

        duplicate_scan = self._find_duplicate_scan(
            idempotency_key=idempotency_key,
            repository_id=repository_id,
            pr_number=pr_number,
            head_sha=head_sha,
        )
        if duplicate_scan:
            return self._duplicate_response(
                scan=duplicate_scan,
                action=str(action),
                repository_full_name=repository_full_name,
                pr_number=pr_number,
                head_sha=head_sha,
                idempotency_key=idempotency_key,
            )

        scan = PullRequestScan(
            organization_id=installation.organization_id,
            repository_id=repository_id,
            github_pr_number=pr_number,
            github_pr_url=pull_request.get("html_url"),
            title=pull_request.get("title"),
            head_sha=head_sha,
            base_sha=(pull_request.get("base") or {}).get("sha"),
            idempotency_key=idempotency_key,
            status=ScanStatus.QUEUED,
            trigger="webhook",
        )
        self.db.add(scan)
        try:
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            duplicate_scan = self.db.scalar(
                select(PullRequestScan).where(PullRequestScan.idempotency_key == idempotency_key)
            )
            if duplicate_scan:
                logger.info(
                    "duplicate_scan_detected",
                    extra={
                        "scan_id": str(duplicate_scan.id),
                        "repository_id": str(repository_id),
                        "pr_number": pr_number,
                        "head_sha": head_sha,
                        "idempotency_key": idempotency_key,
                        "duplicate_reason": "idempotency_key_integrity",
                    },
                )
                return self._duplicate_response(
                    scan=duplicate_scan,
                    action=str(action),
                    repository_full_name=repository_full_name,
                    pr_number=pr_number,
                    head_sha=head_sha,
                    idempotency_key=idempotency_key,
                )
            raise

        AuditService(self.db).log(
            organization_id=installation.organization_id,
            action="scan.queued.webhook",
            target_type="pull_request_scan",
            target_id=str(scan.id),
            metadata={
                "repository": repository_full_name,
                "pr_number": scan.github_pr_number,
                "action": action,
                "sender": (payload.get("sender") or {}).get("login"),
            },
        )
        self.db.commit()
        logger.info(
            "scan_created_from_webhook",
            extra={
                "scan_id": str(scan.id),
                "repository": repository_full_name,
                "repository_id": str(repository_id),
                "pr_number": scan.github_pr_number,
                "head_sha": scan.head_sha,
                "event_action": action,
                "idempotency_key": idempotency_key,
            },
        )

        from app.workers.tasks import run_pr_scan

        run_pr_scan.delay(str(scan.id))
        return GitHubWebhookResponse(accepted=True, action=action, scan_id=scan.id, message="PR scan queued")

    def _idempotency_key(
        self,
        *,
        installation_id: int,
        repository_id: str,
        pr_number: int,
        head_sha: str,
        event_action: str,
    ) -> str:
        raw_key = f"{installation_id}:{repository_id}:{pr_number}:{head_sha}:{event_action}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def _find_duplicate_scan(
        self,
        *,
        idempotency_key: str,
        repository_id,
        pr_number: int,
        head_sha: str,
    ) -> PullRequestScan | None:
        duplicate_scan = self.db.scalar(
            select(PullRequestScan).where(PullRequestScan.idempotency_key == idempotency_key)
        )
        if duplicate_scan:
            logger.info(
                "duplicate_scan_detected",
                extra={
                    "scan_id": str(duplicate_scan.id),
                    "repository_id": str(repository_id),
                    "pr_number": pr_number,
                    "head_sha": head_sha,
                    "idempotency_key": idempotency_key,
                    "duplicate_reason": "idempotency_key",
                },
            )
            return duplicate_scan

        duplicate_scan = self.db.scalar(
            select(PullRequestScan)
            .where(
                PullRequestScan.repository_id == repository_id,
                PullRequestScan.github_pr_number == pr_number,
                PullRequestScan.head_sha == head_sha,
                PullRequestScan.trigger == "webhook",
            )
            .order_by(PullRequestScan.created_at.desc())
            .limit(1)
        )
        if duplicate_scan:
            logger.info(
                "duplicate_scan_detected",
                extra={
                    "scan_id": str(duplicate_scan.id),
                    "repository_id": str(repository_id),
                    "pr_number": pr_number,
                    "head_sha": head_sha,
                    "idempotency_key": idempotency_key,
                    "duplicate_reason": "pull_request_head_sha",
                },
            )
        return duplicate_scan

    def _duplicate_response(
        self,
        *,
        scan: PullRequestScan,
        action: str,
        repository_full_name: str,
        pr_number: int,
        head_sha: str,
        idempotency_key: str,
    ) -> GitHubWebhookResponse:
        logger.info(
            "duplicate_scan_skipped",
            extra={
                "scan_id": str(scan.id),
                "repository": repository_full_name,
                "repository_id": str(scan.repository_id),
                "pr_number": pr_number,
                "head_sha": head_sha,
                "event_action": action,
                "idempotency_key": idempotency_key,
            },
        )
        return GitHubWebhookResponse(
            accepted=True,
            action=action,
            scan_id=scan.id,
            message="Duplicate PR scan skipped; existing scan returned",
        )

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
