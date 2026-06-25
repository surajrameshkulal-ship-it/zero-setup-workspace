"""Real GitHub Draft PR Creator (Phase 10, Step 8).

After validation (and any self-healing) succeeds, this service pushes the
validated workspace changes to a safe `codedna/ai/...` branch and opens a real
**draft** pull request on GitHub. Human approval remains mandatory.

It NEVER merges, deploys, pushes to the default/protected branch, bypasses
approval, modifies secrets, or pushes when validation failed. Duplicate PRs are
prevented (idempotent per execution).
"""

from __future__ import annotations

import base64
import logging
import re
import uuid
from pathlib import Path
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import AppError, NotFoundError
from app.integrations.github import GitHubIntegration
from app.models.draft_pull_request import DraftPullRequest
from app.models.engineering_request import EngineeringRequest, RequestStatus
from app.models.execution_run import ExecutionRun
from app.models.repository import Repository
from app.models.github import GitHubInstallation
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)

PROTECTED_BRANCHES = {"main", "master", "develop", "release", "production"}
FORBIDDEN_FILE = re.compile(r"(^|/)\.env|(^|/)\.git/|secret|credential|\.pem$|\.key$|id_rsa")
SAFE_BRANCH_PREFIX = "codedna/ai/"


class DraftPRClient(Protocol):
    def push_branch(
        self,
        *,
        owner: str,
        repo: str,
        installation_id: int,
        branch: str,
        base_branch: str,
        files: list[tuple[str, str]],
        deletions: list[str],
        message: str,
    ) -> dict: ...

    def open_draft_pull_request(
        self, *, owner: str, repo: str, installation_id: int, head: str, base: str, title: str, body: str
    ) -> dict: ...


class DefaultDraftPRClient:
    """Real client backed by the existing GitHub integration."""

    def __init__(self, integration: GitHubIntegration | None = None) -> None:
        self.gh = integration or GitHubIntegration()

    def push_branch(self, *, owner, repo, installation_id, branch, base_branch, files, deletions, message) -> dict:
        token = self.gh.get_installation_token(installation_id)
        base_sha = self.gh.get_branch_sha(token=token, owner=owner, repo=repo, branch=base_branch)
        self.gh.create_branch(token=token, owner=owner, repo=repo, branch=branch, sha=base_sha)
        for path, content in files:
            existing = self.gh.get_content_sha(token=token, owner=owner, repo=repo, path=path, ref=branch)
            self.gh.put_file(
                token=token,
                owner=owner,
                repo=repo,
                path=path,
                content_b64=base64.b64encode(content.encode("utf-8")).decode("ascii"),
                message=message,
                branch=branch,
                sha=existing,
            )
        for path in deletions:
            existing = self.gh.get_content_sha(token=token, owner=owner, repo=repo, path=path, ref=branch)
            if existing:
                self.gh.delete_file(
                    token=token, owner=owner, repo=repo, path=path, message=message, branch=branch, sha=existing
                )
        return {"branch": branch, "base_sha": base_sha}

    def open_draft_pull_request(self, *, owner, repo, installation_id, head, base, title, body) -> dict:
        token = self.gh.get_installation_token(installation_id)
        pr = self.gh.create_pull_request(
            token=token, owner=owner, repo=repo, head=head, base=base, title=title, body=body, draft=True
        )
        return {"number": pr.get("number"), "html_url": pr.get("html_url")}


class GitHubDraftPRCreator:
    def __init__(self, db: Session, *, client: DraftPRClient | None = None) -> None:
        self.db = db
        self.audit = AuditService(db)
        self.client = client or DefaultDraftPRClient()

    def create(
        self,
        *,
        engineering_request_id: uuid.UUID,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
    ) -> DraftPullRequest:
        request = self._require_request(engineering_request_id, organization_id)
        draft = self.db.scalar(
            select(DraftPullRequest).where(
                DraftPullRequest.engineering_request_id == request.id,
                DraftPullRequest.organization_id == organization_id,
            )
        )
        if draft is None:
            raise NotFoundError("Draft pull request metadata not found; run the pipeline first.")

        # Idempotency: never create a duplicate PR for the same execution.
        if draft.is_pushed and draft.github_pr_url:
            self._audit(organization_id, actor_user_id, "draft_pr_creation_skipped", request, {"reason": "already_created"})
            return draft

        run = self.db.scalar(
            select(ExecutionRun).where(
                ExecutionRun.engineering_request_id == request.id,
                ExecutionRun.organization_id == organization_id,
            )
        )

        self._audit(organization_id, actor_user_id, "draft_pr_creation_started", request, {})
        try:
            repository, installation = self._validate_preconditions(request, draft, run, organization_id)

            files, deletions = self._collect_changes(run, draft)
            self._reject_forbidden(files, deletions)

            push = self.client.push_branch(
                owner=repository.owner,
                repo=repository.name,
                installation_id=installation.installation_id,
                branch=draft.branch_name,
                base_branch=draft.base_branch or repository.default_branch,
                files=files,
                deletions=deletions,
                message=draft.commit_plan[0]["message"] if draft.commit_plan else draft.title,
            )
            self._audit(
                organization_id, actor_user_id, "draft_pr_branch_pushed", request,
                {"branch": draft.branch_name, "base": draft.base_branch},
            )

            body = self._pr_body(draft, run)
            pr = self.client.open_draft_pull_request(
                owner=repository.owner,
                repo=repository.name,
                installation_id=installation.installation_id,
                head=draft.branch_name,
                base=draft.base_branch or repository.default_branch,
                title=draft.title,
                body=body,
            )

            draft.is_pushed = True
            draft.status = "open"
            draft.github_pr_number = pr.get("number")
            draft.github_pr_url = pr.get("html_url")
            draft.body = body
            self.db.flush()
            self._audit(
                organization_id, actor_user_id, "draft_pr_created", request,
                {"github_pr_url": draft.github_pr_url, "github_pr_number": draft.github_pr_number},
            )
            self.db.commit()
            self.db.refresh(draft)
            logger.info("draft_pr_created", extra={"request_id": str(request.id), "pr": draft.github_pr_url})
            return draft
        except AppError:
            self._audit(organization_id, actor_user_id, "draft_pr_creation_skipped", request, {})
            self.db.commit()
            raise
        except Exception as exc:  # noqa: BLE001
            self._audit(organization_id, actor_user_id, "draft_pr_creation_failed", request, {"error": str(exc)[:300]})
            self.db.commit()
            logger.warning("draft_pr_creation_failed", extra={"request_id": str(request.id), "error": str(exc)[:300]})
            raise

    # -- preconditions ---------------------------------------------------------

    def _validate_preconditions(self, request, draft, run, organization_id) -> tuple[Repository, GitHubInstallation]:
        if request.status != RequestStatus.APPROVED:
            raise AppError("Refusing: engineering request is not approved.")
        if run is None or run.status != "completed":
            raise AppError("Refusing: execution validation has not passed.")
        healing = (run.report or {}).get("healing")
        if healing is not None and healing.get("status") not in ("healed",):
            raise AppError("Refusing: self-healing did not succeed.")

        branch = (draft.branch_name or "").strip()
        default_branch = (draft.base_branch or "").strip().lower()
        if not branch.startswith(SAFE_BRANCH_PREFIX):
            raise AppError("Refusing: branch is not a safe 'codedna/ai/...' branch.")
        if branch.lower() in PROTECTED_BRANCHES or (default_branch and branch.lower() == default_branch):
            raise AppError("Refusing: cannot push to the default/protected branch.")

        if request.repository_id is None:
            raise AppError("Refusing: request has no repository.")
        repository = self.db.get(Repository, request.repository_id)
        if repository is None or not repository.is_active or repository.github_installation_id is None:
            raise AppError("Refusing: repository is not connected to a GitHub installation.")
        installation = self.db.get(GitHubInstallation, repository.github_installation_id)
        if installation is None:
            raise AppError("Refusing: GitHub installation is missing.")

        if run.workspace_path and not Path(run.workspace_path).is_dir():
            raise AppError("Refusing: workspace is invalid.")
        return repository, installation

    def _collect_changes(self, run: ExecutionRun, draft: DraftPullRequest) -> tuple[list[tuple[str, str]], list[str]]:
        plan = run.code_plan or {} if run else {}
        modify = list(plan.get("files_to_modify", []))
        create = list(plan.get("files_to_create", []))
        delete = list(plan.get("files_to_delete", []))
        # Include any files touched during self-healing iterations.
        for iteration in ((run.report or {}).get("healing") or {}).get("iterations", []) if run else []:
            modify.extend(iteration.get("files_changed", []))

        workspace = Path(run.workspace_path) if run and run.workspace_path else None
        files: list[tuple[str, str]] = []
        seen: set[str] = set()
        for rel in create + modify:
            if rel in seen or rel in delete:
                continue
            seen.add(rel)
            if workspace is None:
                continue
            abs_path = workspace / rel
            if abs_path.is_file():
                files.append((rel, abs_path.read_text(encoding="utf-8", errors="replace")))
        return files, [d for d in delete if d]

    def _reject_forbidden(self, files: list[tuple[str, str]], deletions: list[str]) -> None:
        for path in [p for p, _ in files] + deletions:
            if FORBIDDEN_FILE.search(path.lower()):
                raise AppError(f"Refusing: change set includes a protected/secret file ({path}).")

    def _pr_body(self, draft: DraftPullRequest, run: ExecutionRun | None) -> str:
        report = (run.report if run else {}) or {}
        healing = report.get("healing") or {}
        lines = [
            draft.body or "",
            "",
            "---",
            "### Execution report",
            f"- Validation: passed",
            f"- Self-healing: {healing.get('status', 'not needed')}"
            + (f" ({healing.get('fixes_applied', 0)} fix(es))" if healing else ""),
            f"- Workspace branch: `{draft.branch_name}` → `{draft.base_branch}`",
            "",
            "> 🔒 **Human review required.** This draft PR was prepared by CodeDNA AI "
            "after passing validation. It has NOT been merged or deployed.",
        ]
        return "\n".join(lines)

    def _require_request(self, engineering_request_id: uuid.UUID, organization_id: uuid.UUID) -> EngineeringRequest:
        request = self.db.scalar(
            select(EngineeringRequest)
            .options(joinedload(EngineeringRequest.repository))
            .where(
                EngineeringRequest.id == engineering_request_id,
                EngineeringRequest.organization_id == organization_id,
            )
        )
        if not request:
            raise NotFoundError("Engineering request not found")
        return request

    def _audit(self, organization_id, actor_user_id, action, request, metadata) -> None:
        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type="engineering_request",
            target_id=str(request.id),
            metadata=metadata,
        )
