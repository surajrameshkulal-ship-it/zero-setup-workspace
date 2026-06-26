"""Real GitHub Draft PR Creator (Phase 10, Step 8).

After validation passes, this service materializes the repository, generates and
applies the changes inside an isolated workspace, pushes them to a safe
`codedna/ai/...` branch, and opens a real **draft** pull request on GitHub.

The validation gate is the passed `ValidationRun` produced by the validation
step (NOT a separate ExecutionRun). It NEVER merges, deploys, pushes to the
default/protected branch, bypasses validation, modifies secrets, or pushes when
validation has not passed. Duplicate PRs are prevented (idempotent).
"""

from __future__ import annotations

import base64
import logging
import re
import uuid
from pathlib import Path
from typing import Callable, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import AppError, NotFoundError
from app.integrations.github import GitHubIntegration
from app.models.draft_pull_request import DraftPullRequest
from app.models.engineering_request import EngineeringRequest, RequestStatus
from app.models.github import GitHubInstallation
from app.models.repository import Repository
from app.models.validation_run import ValidationRun
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)

PROTECTED_BRANCHES = {"main", "master", "develop", "release", "production"}
FORBIDDEN_FILE = re.compile(r"(^|/)\.env|(^|/)\.git/|secret|credential|\.pem$|\.key$|id_rsa")
SAFE_BRANCH_PREFIX = "codedna/ai/"

# Builds the real change set: returns (files=[(path, content)], deletions=[path]).
ChangeBuilder = Callable[..., tuple[list[tuple[str, str]], list[str]]]


class DraftPRClient(Protocol):
    def push_branch(
        self, *, owner: str, repo: str, installation_id: int, branch: str, base_branch: str,
        files: list[tuple[str, str]], deletions: list[str], message: str,
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
        logger.info("branch_created", extra={"owner": owner, "repo": repo, "branch": branch, "base_sha": base_sha})
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
            logger.info("commit_created", extra={"owner": owner, "repo": repo, "branch": branch, "path": path})
        for path in deletions:
            existing = self.gh.get_content_sha(token=token, owner=owner, repo=repo, path=path, ref=branch)
            if existing:
                self.gh.delete_file(
                    token=token, owner=owner, repo=repo, path=path, message=message, branch=branch, sha=existing
                )
                logger.info("commit_created", extra={"owner": owner, "repo": repo, "branch": branch, "path": path, "deleted": True})
        logger.info("branch_pushed", extra={"owner": owner, "repo": repo, "branch": branch, "file_count": len(files)})
        return {"branch": branch, "base_sha": base_sha}

    def open_draft_pull_request(self, *, owner, repo, installation_id, head, base, title, body) -> dict:
        token = self.gh.get_installation_token(installation_id)
        pr = self.gh.create_pull_request(
            token=token, owner=owner, repo=repo, head=head, base=base, title=title, body=body, draft=True
        )
        logger.info(
            "github_draft_pr_created",
            extra={"owner": owner, "repo": repo, "number": pr.get("number"), "html_url": pr.get("html_url")},
        )
        return {"number": pr.get("number"), "html_url": pr.get("html_url")}


class GitHubDraftPRCreator:
    def __init__(
        self,
        db: Session,
        *,
        client: DraftPRClient | None = None,
        change_builder: ChangeBuilder | None = None,
        workspace_manager=None,
    ) -> None:
        self.db = db
        self.audit = AuditService(db)
        self.client = client or DefaultDraftPRClient()
        self.change_builder = change_builder or self._default_build_changes
        self.workspace_manager = workspace_manager

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
            raise NotFoundError("Draft pull request metadata not found; prepare the draft first.")

        # Idempotency: never create a duplicate PR.
        if draft.is_pushed and draft.github_pr_url:
            self._audit(organization_id, actor_user_id, "draft_pr_creation_skipped", request, {"reason": "already_created"})
            return draft

        validation = self.db.scalar(
            select(ValidationRun).where(
                ValidationRun.engineering_request_id == request.id,
                ValidationRun.organization_id == organization_id,
            )
        )
        # Diagnostic logging before any refusal (validation state the gate sees).
        logger.info(
            "draft_pr_precondition_check",
            extra={
                "request_id": str(request.id),
                "validation_run_id": str(validation.id) if validation else None,
                "validation_status": validation.status if validation else None,
                "draft_branch": draft.branch_name,
                "draft_is_pushed": draft.is_pushed,
            },
        )

        self._audit(organization_id, actor_user_id, "draft_pr_creation_started", request, {})
        logger.info("draft_pr_creation_started", extra={"request_id": str(request.id)})
        try:
            repository, installation = self._validate_preconditions(request, draft, validation)

            files, deletions = self.change_builder(
                request=request,
                draft=draft,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
            )
            self._reject_forbidden(files, deletions)
            if not files and not deletions:
                logger.warning("no_workspace_changes_detected", extra={"request_id": str(request.id)})
                raise AppError("No changes were applied from code generation plan.")

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
                {"branch": draft.branch_name, "base": draft.base_branch, "files": len(files)},
            )

            body = self._pr_body(draft, validation)
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
            self.db.commit()
            raise
        except Exception as exc:  # noqa: BLE001
            self._audit(organization_id, actor_user_id, "draft_pr_creation_failed", request, {"error": str(exc)[:300]})
            self.db.commit()
            logger.warning("draft_pr_creation_failed", extra={"request_id": str(request.id), "error": str(exc)[:300]})
            raise

    # -- preconditions ---------------------------------------------------------

    def _validate_preconditions(
        self, request, draft, validation: ValidationRun | None
    ) -> tuple[Repository, GitHubInstallation]:
        if request.status != RequestStatus.APPROVED:
            raise AppError("Refusing: engineering request is not approved.")

        # Validation gate: the ValidationRun produced by the validation step must have passed.
        if validation is None or validation.status != "passed":
            status = validation.status if validation else "none"
            self._audit_skip(request, f"validation_not_passed:{status}")
            raise AppError(
                f"Refusing: validation has not passed (validation status: {status}). "
                "Run validation successfully before creating the pull request."
            )

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
        return repository, installation

    # -- default real change builder (materialize -> generate -> apply) --------

    def _default_build_changes(
        self, *, request, draft, organization_id, actor_user_id
    ) -> tuple[list[tuple[str, str]], list[str]]:
        from app.services.agent.code_generation_engine import CodeGenerationEngine
        from app.services.agent.github_source_provider import GitHubTarballSourceProvider
        from app.services.agent.safe_change_applier import SafeChangeApplier
        from app.services.workspace.repository_materializer import RepositoryMaterializer
        from app.services.workspace.secure_workspace_manager import SecureWorkspaceManager, WorkspaceHandle

        wm = self.workspace_manager or SecureWorkspaceManager(db=self.db)

        snapshot = RepositoryMaterializer(self.db, workspace_manager=wm).materialize(
            repository_id=request.repository_id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            target_branch=draft.branch_name,
            source_provider=GitHubTarballSourceProvider(self.db),
        )
        if not snapshot.materialized:
            raise AppError(f"Refusing: repository could not be materialized ({snapshot.reason}).")

        plan = CodeGenerationEngine(self.db).generate(
            engineering_request_id=request.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            materialization=snapshot,
        )
        logger.info(
            "code_generation_file_changes_count",
            extra={
                "request_id": str(request.id),
                "count": len(plan.changes),
                "files": len(plan.files_to_create) + len(plan.files_to_modify) + len(plan.files_to_delete),
            },
        )

        handle = WorkspaceHandle(
            workspace_id="draftpr",
            path=snapshot.workspace_path,
            branch_name=snapshot.target_branch,
            base_branch=snapshot.default_branch,
            max_bytes=wm.max_bytes,
        )
        applier = SafeChangeApplier(workspace_manager=wm, handle=handle, db=self.db)
        result = applier.apply(
            plan.changes, dry_run=False, organization_id=organization_id, actor_user_id=actor_user_id
        )
        logger.info(
            "safe_change_operations_count",
            extra={
                "request_id": str(request.id),
                "applied": len(result.applied_operations),
                "skipped": len(result.skipped_operations),
                "files_changed": len(result.files_changed),
            },
        )

        if not result.files_changed:
            logger.warning(
                "no_workspace_changes_detected",
                extra={
                    "request_id": str(request.id),
                    "skipped_reasons": [s.get("reason") for s in result.skipped_operations],
                },
            )
            raise AppError(
                "No changes were applied from code generation plan. "
                "The AI plan produced no supported, non-empty file operations."
            )

        workspace = Path(snapshot.workspace_path)
        files: list[tuple[str, str]] = []
        deletions: list[str] = []
        for rel in result.files_changed:
            abs_path = workspace / rel
            if abs_path.is_file():
                files.append((rel, abs_path.read_text(encoding="utf-8", errors="replace")))
            else:
                deletions.append(rel)  # changed but absent => deleted
        return files, deletions

    # -- helpers ---------------------------------------------------------------

    def _reject_forbidden(self, files: list[tuple[str, str]], deletions: list[str]) -> None:
        for path in [p for p, _ in files] + deletions:
            if FORBIDDEN_FILE.search(path.lower()):
                raise AppError(f"Refusing: change set includes a protected/secret file ({path}).")

    def _pr_body(self, draft: DraftPullRequest, validation: ValidationRun | None) -> str:
        report = (validation.report if validation else {}) or {}
        lines = [
            draft.body or "",
            "",
            "---",
            "### Validation",
            f"- Status: {validation.status if validation else 'unknown'}",
            f"- Passed checks: {', '.join(report.get('passed', [])) or 'n/a'}",
            f"- Branch: `{draft.branch_name}` → `{draft.base_branch}`",
            "",
            "> 🔒 **Human review required.** This draft PR was prepared by CodeDNA AI "
            "after validation passed. It has NOT been merged or deployed.",
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

    def _audit_skip(self, request, reason: str) -> None:
        logger.warning("draft_pr_creation_skipped", extra={"request_id": str(request.id), "reason": reason})