from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import AppError, NotFoundError
from app.models.code_generation import CodeGenerationPreview
from app.models.draft_pull_request import DraftPullRequest
from app.models.engineering_request import EngineeringRequest, RequestStatus, RequestType
from app.services.audit_service import AuditService
from app.services.execution.github_workspace_manager import GitHubWorkspaceManager

logger = logging.getLogger(__name__)

_COMMIT_TYPE = {
    RequestType.BUG: "fix",
    RequestType.FEATURE: "feat",
    RequestType.REFACTOR: "refactor",
    RequestType.DOCS: "docs",
    RequestType.SECURITY: "fix",
    RequestType.PERFORMANCE: "perf",
    RequestType.OTHER: "chore",
}


class DraftPullRequestService:
    """Prepares draft pull-request METADATA only.

    Never creates a branch on the remote, pushes commits, opens a PR, merges,
    or deploys. Everything stays human-gated.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)
        self.workspace = GitHubWorkspaceManager()

    # -- queries ---------------------------------------------------------------

    def get_for_request(
        self, engineering_request_id: uuid.UUID, organization_id: uuid.UUID
    ) -> DraftPullRequest:
        draft = self.db.scalar(
            select(DraftPullRequest).where(
                DraftPullRequest.engineering_request_id == engineering_request_id,
                DraftPullRequest.organization_id == organization_id,
            )
        )
        if not draft:
            raise NotFoundError("Draft pull request not found")
        return draft

    # -- command ---------------------------------------------------------------

    def generate(
        self,
        *,
        engineering_request_id: uuid.UUID,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
    ) -> DraftPullRequest:
        request = self._get_request(engineering_request_id, organization_id)
        if request.status != RequestStatus.APPROVED:
            raise AppError("A draft pull request can only be prepared for an approved request")

        repository = request.repository
        branch_name = self.workspace.create_branch_name(request)
        base_branch = self.workspace.verify_default_branch(repository) or "main"

        # Defensive: never target a protected/default branch as the working branch.
        if not self.workspace.is_branch_safe(branch_name, base_branch):
            raise AppError("Refusing to prepare a draft PR with an unsafe working branch")

        code_preview = self.db.scalar(
            select(CodeGenerationPreview).where(
                CodeGenerationPreview.engineering_request_id == request.id
            )
        )

        title = f"[CodeDNA AI] {request.title}"
        commit_plan = self._commit_plan(request, code_preview)
        labels = self._labels(request)
        body = self._body(request, branch_name, base_branch, commit_plan)

        draft = self.db.scalar(
            select(DraftPullRequest).where(DraftPullRequest.engineering_request_id == request.id)
        )
        if draft is None:
            draft = DraftPullRequest(
                organization_id=organization_id,
                engineering_request_id=request.id,
                repository_id=request.repository_id,
            )
            self.db.add(draft)

        draft.repository_id = request.repository_id
        draft.branch_name = branch_name
        draft.base_branch = base_branch
        draft.title = title
        draft.body = body
        draft.commit_plan = commit_plan
        draft.labels = labels
        draft.status = "draft"
        draft.is_pushed = False
        draft.human_approval_required = True

        self.db.flush()
        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="draft_pull_request_prepared",
            target_type="engineering_request",
            target_id=str(request.id),
            metadata={"branch_name": branch_name, "base_branch": base_branch},
        )
        self.db.commit()
        self.db.refresh(draft)
        return draft

    # -- builders --------------------------------------------------------------

    def _commit_plan(
        self, request: EngineeringRequest, code_preview: CodeGenerationPreview | None
    ) -> list[dict]:
        prefix = _COMMIT_TYPE.get(request.request_type, "chore")
        scope = "security" if request.request_type == RequestType.SECURITY else None
        header = f"{prefix}({scope}): {request.title}" if scope else f"{prefix}: {request.title}"

        files: list[str] = []
        if code_preview and code_preview.affected_files:
            files = [str(f.get("path")) for f in code_preview.affected_files if isinstance(f, dict) and f.get("path")]
        elif request.affected_files:
            files = [str(f.get("path")) for f in request.affected_files if isinstance(f, dict) and f.get("path")]

        return [{"order": 1, "message": header, "files": files}]

    @staticmethod
    def _labels(request: EngineeringRequest) -> list[str]:
        labels = ["codedna-ai", "ai-generated", "needs-human-review", f"type:{request.request_type.value}"]
        if request.risk_level is not None:
            labels.append(f"risk:{request.risk_level.value}")
        return labels

    @staticmethod
    def _body(
        request: EngineeringRequest, branch_name: str, base_branch: str, commit_plan: list[dict]
    ) -> str:
        plan = "\n".join(f"- {step}" for step in (request.implementation_plan or [])) or "- (see request)"
        commits = "\n".join(f"- `{c['message']}` ({len(c.get('files', []))} file(s))" for c in commit_plan)
        risk = request.risk_level.value if request.risk_level else "unspecified"
        return (
            "## CodeDNA AI — Draft Pull Request (not yet opened)\n\n"
            "> This is **draft metadata only**. CodeDNA has **not** created a branch on "
            "the remote, pushed commits, opened a pull request, merged, or deployed. "
            "A human must review and perform any GitHub action.\n\n"
            f"**Request:** {request.title}\n"
            f"**Type:** {request.request_type.value}  |  **Risk:** {risk}\n"
            f"**Proposed branch:** `{branch_name}` → `{base_branch}`\n\n"
            f"### Summary\n{request.ai_summary or request.description}\n\n"
            f"### Implementation plan\n{plan}\n\n"
            f"### Commit plan\n{commits}\n\n"
            "### Review checklist\n"
            "- [ ] Diff reviewed by a human\n"
            "- [ ] Tests pass\n"
            "- [ ] No protected/secret files changed\n"
            "- [ ] Approved to open the pull request\n"
        )

    def _get_request(
        self, engineering_request_id: uuid.UUID, organization_id: uuid.UUID
    ) -> EngineeringRequest:
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
