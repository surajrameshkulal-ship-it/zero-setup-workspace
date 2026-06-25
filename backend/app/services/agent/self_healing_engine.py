"""AI Self-Healing Engine (Phase 10, Step 7).

When validation fails, this engine analyzes the failures, generates structured
fixes via the AI Provider Router, applies them through the Safe Change Applier
(workspace only), and re-runs validation — repeating until validation passes or
a retry limit is reached. If healing fails, all applied fixes are rolled back.

Human approval remains mandatory. The engine never merges, deploys, pushes,
performs any Git operation, or modifies files outside the workspace.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, IntegrationError, NotFoundError
from app.services.agent.safe_change_applier import SafeChangeApplier
from app.services.ai.provider_router import AIProviderRouter
from app.services.audit_service import AuditService
from app.services.workspace.secure_workspace_manager import SecureWorkspaceManager, WorkspaceHandle

logger = logging.getLogger(__name__)

# (context, attempt) -> list of check dicts {name, status, details}
Validator = Callable[[dict, int], list[dict]]
# (failures, context) -> list of change dicts for the Safe Change Applier
FixGenerator = Callable[[list[dict], dict], list[dict]]


@dataclass
class HealingResult:
    status: str  # healed | failed | retry_limit
    iterations: list[dict] = field(default_factory=list)
    fixes_applied: int = 0
    remaining_failures: list[str] = field(default_factory=list)
    final_validation: dict = field(default_factory=dict)
    rolled_back: bool = False
    reason: str | None = None

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "iterations": self.iterations,
            "fixes_applied": self.fixes_applied,
            "remaining_failures": self.remaining_failures,
            "final_validation": self.final_validation,
            "rolled_back": self.rolled_back,
            "reason": self.reason,
        }


class SelfHealingEngine:
    def __init__(self, db: Session, *, workspace_manager: SecureWorkspaceManager, router: AIProviderRouter | None = None) -> None:
        self.db = db
        self.audit = AuditService(db)
        self.workspace_manager = workspace_manager
        self.router = router or AIProviderRouter()

    def heal(
        self,
        *,
        request,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        handle: WorkspaceHandle,
        initial_checks: list[dict],
        validator: Validator,
        repository_dna: Any | None = None,
        code_plan: dict | None = None,
        fix_generator: FixGenerator | None = None,
        max_retries: int | None = None,
    ) -> HealingResult:
        # Org isolation: the request must belong to the caller's organization.
        if getattr(request, "organization_id", None) != organization_id:
            raise NotFoundError("Engineering request not found")

        max_retries = max_retries or settings.self_healing_max_retries
        applier = SafeChangeApplier(workspace_manager=self.workspace_manager, handle=handle, db=self.db)
        context = {
            "request": request,
            "repository_dna": repository_dna,
            "code_plan": code_plan,
            "languages": getattr(repository_dna, "languages", None) or [],
        }

        failures = [c for c in initial_checks if c.get("status") == "failed"]
        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="self_healing_started",
            target_type="engineering_request",
            target_id=str(request.id),
            metadata={"initial_failures": [c.get("name") for c in failures], "max_retries": max_retries},
        )
        logger.info("self_healing_started", extra={"request_id": str(request.id), "failures": len(failures)})

        if not failures:
            return HealingResult(status="healed", final_validation={"passed": True, "checks": initial_checks})

        snapshots: list[dict] = []
        iterations: list[dict] = []
        total_fixes = 0
        last_checks = initial_checks

        for attempt in range(1, max_retries + 1):
            self.audit.log(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="self_healing_iteration",
                target_type="engineering_request",
                target_id=str(request.id),
                metadata={"iteration": attempt, "failures": [c.get("name") for c in failures]},
            )
            logger.info("self_healing_iteration", extra={"request_id": str(request.id), "iteration": attempt})

            try:
                fixes = (fix_generator or self._generate_fixes)(failures, context)
            except IntegrationError as exc:
                return self._fail(
                    request, organization_id, actor_user_id, applier, snapshots, iterations,
                    total_fixes, failures, last_checks, reason=f"AI provider unavailable: {exc}",
                )

            if not fixes:
                return self._fail(
                    request, organization_id, actor_user_id, applier, snapshots, iterations,
                    total_fixes, failures, last_checks, reason="No fixes were generated.",
                )

            try:
                apply_result = applier.apply(
                    fixes, dry_run=False, organization_id=organization_id, actor_user_id=actor_user_id
                )
            except AppError as exc:
                # e.g. a fix targeted a protected/forbidden file — reject and roll back.
                return self._fail(
                    request, organization_id, actor_user_id, applier, snapshots, iterations,
                    total_fixes, failures, last_checks, reason=f"Fix rejected by safety checks: {exc}",
                )

            snapshots.append(apply_result.rollback_snapshot)
            total_fixes += len(apply_result.applied_operations)

            checks = validator(context, attempt)
            failed = [c for c in checks if c.get("status") == "failed"]
            iterations.append(
                {
                    "iteration": attempt,
                    "analyzed_failures": [c.get("name") for c in failures],
                    "files_changed": apply_result.files_changed,
                    "fixes_applied": len(apply_result.applied_operations),
                    "validation_passed": not failed,
                }
            )
            last_checks = checks
            failures = failed

            if not failed:
                self.audit.log(
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    action="self_healing_success",
                    target_type="engineering_request",
                    target_id=str(request.id),
                    metadata={"iterations": attempt, "fixes_applied": total_fixes},
                )
                logger.info("self_healing_success", extra={"request_id": str(request.id), "iterations": attempt})
                return HealingResult(
                    status="healed",
                    iterations=iterations,
                    fixes_applied=total_fixes,
                    remaining_failures=[],
                    final_validation={"passed": True, "checks": checks},
                    rolled_back=False,
                )

        # Retry limit reached without success: roll back everything.
        self._rollback(applier, snapshots, organization_id, actor_user_id)
        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="self_healing_retry_limit",
            target_type="engineering_request",
            target_id=str(request.id),
            metadata={"max_retries": max_retries, "remaining_failures": [c.get("name") for c in failures]},
        )
        logger.warning("self_healing_retry_limit", extra={"request_id": str(request.id), "max_retries": max_retries})
        return HealingResult(
            status="retry_limit",
            iterations=iterations,
            fixes_applied=total_fixes,
            remaining_failures=[c.get("name") for c in failures],
            final_validation={"passed": False, "checks": last_checks},
            rolled_back=True,
            reason=f"Validation still failing after {max_retries} healing attempt(s).",
        )

    # -- helpers ---------------------------------------------------------------

    def _fail(
        self, request, organization_id, actor_user_id, applier, snapshots, iterations,
        total_fixes, failures, last_checks, *, reason: str,
    ) -> HealingResult:
        self._rollback(applier, snapshots, organization_id, actor_user_id)
        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="self_healing_failed",
            target_type="engineering_request",
            target_id=str(request.id),
            metadata={"reason": reason},
        )
        logger.warning("self_healing_failed", extra={"request_id": str(request.id), "reason": reason})
        return HealingResult(
            status="failed",
            iterations=iterations,
            fixes_applied=total_fixes,
            remaining_failures=[c.get("name") for c in failures],
            final_validation={"passed": False, "checks": last_checks},
            rolled_back=bool(snapshots),
            reason=reason,
        )

    def _rollback(self, applier: SafeChangeApplier, snapshots: list[dict], organization_id, actor_user_id) -> None:
        # Restore the workspace to its pre-healing state (reverse order).
        for snapshot in reversed(snapshots):
            if snapshot:
                try:
                    applier.rollback(snapshot, organization_id=organization_id, actor_user_id=actor_user_id)
                except Exception:  # noqa: BLE001 - best effort
                    logger.warning("self_healing_rollback_error")

    def _generate_fixes(self, failures: list[dict], context: dict) -> list[dict]:
        raw = self._call_ai(self._build_prompt(failures, context))
        parsed = self._parse(raw) if raw else None
        if not parsed:
            return []
        changes = parsed.get("changes")
        return changes if isinstance(changes, list) else []

    def _call_ai(self, prompt: str) -> str | None:
        if not settings.ai_review_enabled:
            return None
        return self.router.generate(prompt)  # IntegrationError propagates (provider unavailable)

    def _build_prompt(self, failures: list[dict], context: dict) -> str:
        request = context["request"]
        failure_lines = "\n".join(
            f"- {c.get('name')}: {c.get('details', '')}" for c in failures
        ) or "- (unspecified)"
        languages = ", ".join(map(str, context.get("languages", []))) or "unknown"
        return (
            "You are an AI engineer fixing validation failures. Return ONLY a JSON "
            "change plan for the Safe Change Applier. Do NOT commit, push, deploy, or "
            "touch files outside the workspace.\n\n"
            f"Request: {request.title}\nLanguages: {languages}\n"
            f"Failing checks:\n{failure_lines}\n\n"
            'Return ONLY valid JSON: {"changes": [{"path": str, "operations": '
            '[{"type": "create_file|replace_file|insert_after|insert_before|replace_block|delete_file", '
            '"target": str, "content": str}]}]}\n'
        )

    def _parse(self, raw: str | None) -> dict | None:
        if not raw:
            return None
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1] if text.count("```") >= 2 else text.strip("`")
            if text.lstrip().lower().startswith("json"):
                text = text.lstrip()[4:]
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            return None
        return data if isinstance(data, dict) else None
