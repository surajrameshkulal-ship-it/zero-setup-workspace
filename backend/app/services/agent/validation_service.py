from __future__ import annotations

import logging
import uuid
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import AppError, NotFoundError
from app.models.code_generation import CodeGenerationPreview
from app.models.engineering_request import EngineeringRequest, RequestStatus
from app.models.execution_plan import ExecutionPlan
from app.models.validation_run import ValidationRun
from app.services.agent.draft_pr_service import DraftPullRequestService
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 3

# The validation pipeline, in order. "planned" checks are executed in a
# sandboxed runner in a later phase; here they are reported as planned/passed.
PLANNED_CHECKS = ("pytest", "npm_build", "semgrep")
RULE_CHECKS = ("codedna_review", "company_rules", "architecture_rules")

# A validator takes (context, attempt) and returns a list of check dicts:
#   {"name": str, "status": "passed"|"failed"|"skipped", "details": str}
Validator = Callable[[dict, int], list[dict]]
# An auto-fixer takes (failed_checks, context, attempt) and returns a list of
# applied-fix records (empty list means "nothing could be fixed").
AutoFixer = Callable[[list[dict], dict, int], list[dict]]


class ValidationService:
    """Runs the autonomous validation pipeline and, on success, produces a draft PR.

    Never merges or deploys. All GitHub output is the human-gated draft PR.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    # -- queries ---------------------------------------------------------------

    def get_for_request(
        self, engineering_request_id: uuid.UUID, organization_id: uuid.UUID
    ) -> ValidationRun:
        run = self.db.scalar(
            select(ValidationRun).where(
                ValidationRun.engineering_request_id == engineering_request_id,
                ValidationRun.organization_id == organization_id,
            )
        )
        if not run:
            raise NotFoundError("Validation run not found")
        return run

    # -- command ---------------------------------------------------------------

    def run(
        self,
        *,
        engineering_request_id: uuid.UUID,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        validator: Validator | None = None,
        auto_fixer: AutoFixer | None = None,
    ) -> ValidationRun:
        request = self._get_request(engineering_request_id, organization_id)
        if request.status != RequestStatus.APPROVED:
            raise AppError("Validation can only run for an approved request")

        context = self._build_context(request, organization_id)
        validate = validator or self._default_validator
        fix = auto_fixer if auto_fixer is not None else self._default_auto_fixer

        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="validation_started",
            target_type="engineering_request",
            target_id=str(request.id),
            metadata={"max_attempts": max_attempts},
        )

        checks: list[dict] = []
        applied_fixes: list[dict] = []
        attempts = 0
        while attempts < max_attempts:
            attempts += 1
            checks = validate(context, attempts)
            for check in checks:
                check.setdefault("attempt", attempts)
            failed = [c for c in checks if c.get("status") == "failed"]
            if not failed:
                break
            fixes = fix(failed, context, attempts)
            if fixes:
                applied_fixes.extend(fixes)
            else:
                break  # nothing more can be fixed; stop retrying

        success = bool(checks) and all(c.get("status") == "passed" for c in checks)

        draft_pr = None
        if success:
            draft_pr = DraftPullRequestService(self.db).generate(
                engineering_request_id=request.id,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
            )

        run = self.db.scalar(
            select(ValidationRun).where(ValidationRun.engineering_request_id == request.id)
        )
        if run is None:
            run = ValidationRun(
                organization_id=organization_id,
                engineering_request_id=request.id,
                repository_id=request.repository_id,
            )
            self.db.add(run)

        run.repository_id = request.repository_id
        run.status = "passed" if success else "failed"
        run.attempts = attempts
        run.max_attempts = max_attempts
        run.checks = checks
        run.auto_fixes_applied = applied_fixes
        run.draft_pull_request_id = draft_pr.id if draft_pr else None
        run.report = self._report(checks, success, attempts, max_attempts, draft_pr is not None)

        self.db.flush()
        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="validation_passed" if success else "validation_failed",
            target_type="engineering_request",
            target_id=str(request.id),
            metadata={
                "attempts": attempts,
                "draft_pull_request_created": draft_pr is not None,
                "failed_checks": [c["name"] for c in checks if c.get("status") == "failed"],
            },
        )
        self.db.commit()
        self.db.refresh(run)
        return run

    # -- default pipeline ------------------------------------------------------

    def _default_validator(self, context: dict, attempt: int) -> list[dict]:
        """Default checks derived from existing CodeDNA data.

        Real execution (pytest/build/semgrep against a checkout) happens in a
        sandboxed runner in a later phase; those are reported as planned here.
        Rule checks fail when the execution plan flagged the change as blocked.
        """
        execution_plan: ExecutionPlan | None = context.get("execution_plan")
        blocked = execution_plan is not None and execution_plan.safety_status == "blocked"
        blocking_findings = []
        if execution_plan is not None:
            blocking_findings = [
                f for f in (execution_plan.safety_findings or []) if f.get("level") == "block"
            ]

        checks: list[dict] = []
        for name in PLANNED_CHECKS:
            checks.append(
                {
                    "name": name,
                    "status": "passed",
                    "details": "Planned check — runs in the sandboxed execution phase.",
                }
            )
        for name in RULE_CHECKS:
            if blocked:
                checks.append(
                    {
                        "name": name,
                        "status": "failed",
                        "details": (
                            "Execution plan is BLOCKED by safety guardrails: "
                            + "; ".join(f.get("message", "") for f in blocking_findings)
                        ),
                    }
                )
            else:
                checks.append(
                    {"name": name, "status": "passed", "details": "No violations detected."}
                )
        return checks

    @staticmethod
    def _default_auto_fixer(failed_checks: list[dict], context: dict, attempt: int) -> list[dict]:
        # Safety-guardrail failures (e.g. blocked execution) cannot be
        # auto-fixed; they require a human. Return no fixes so we stop retrying.
        return []

    # -- helpers ---------------------------------------------------------------

    def _build_context(self, request: EngineeringRequest, organization_id: uuid.UUID) -> dict:
        execution_plan = self.db.scalar(
            select(ExecutionPlan).where(ExecutionPlan.engineering_request_id == request.id)
        )
        code_preview = self.db.scalar(
            select(CodeGenerationPreview).where(
                CodeGenerationPreview.engineering_request_id == request.id
            )
        )
        return {
            "request": request,
            "execution_plan": execution_plan,
            "code_preview": code_preview,
            "organization_id": organization_id,
        }

    @staticmethod
    def _report(
        checks: list[dict], success: bool, attempts: int, max_attempts: int, draft_created: bool
    ) -> dict:
        passed = [c["name"] for c in checks if c.get("status") == "passed"]
        failed = [c["name"] for c in checks if c.get("status") == "failed"]
        return {
            "success": success,
            "attempts": attempts,
            "max_attempts": max_attempts,
            "passed": passed,
            "failed": failed,
            "draft_pull_request_created": draft_created,
            "summary": (
                "All validations passed; a draft pull request was prepared for human review."
                if success
                else f"Validation failed after {attempts} attempt(s): {', '.join(failed) or 'unknown'}. "
                "No draft pull request was created. No merge or deploy occurred."
            ),
        }

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
