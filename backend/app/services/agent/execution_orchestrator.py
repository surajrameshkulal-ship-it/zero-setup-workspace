"""Execution Orchestrator (Phase 10, Step 5).

Coordinates the already-implemented Phase 10 services into ONE human-gated
pipeline. It owns sequencing, state tracking, resume, retries, cancellation,
timeout handling, rollback, and audit logging — it does not re-implement any
stage's logic.

Pipeline (each stage delegates to an existing service):
  1. approved engineering request  (precondition)
  2. Repository Materializer
  3. AI Code Generation Engine
  4. Safe Change Applier            (workspace only)
  5. Validation Pipeline            (prepares the draft PR on success)
  6. Draft Pull Request             (fetched/confirmed)

Never merges, deploys, or bypasses human approval.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import AppError, NotFoundError
from app.models.engineering_request import EngineeringRequest, RequestStatus
from app.models.execution_run import ExecutionRun
from app.services.agent.code_generation_engine import CodeGenerationEngine
from app.services.agent.draft_pr_service import DraftPullRequestService
from app.services.agent.safe_change_applier import SafeChangeApplier
from app.services.agent.validation_service import ValidationService
from app.services.audit_service import AuditService
from app.services.workspace.repository_materializer import RepositoryMaterializer
from app.services.workspace.secure_workspace_manager import (
    SecureWorkspaceManager,
    WorkspaceHandle,
)

logger = logging.getLogger(__name__)

STAGES = ("materialize", "generate", "apply", "validate", "draft_pr")
TERMINAL_OK = "completed"


@dataclass
class _Context:
    request: EngineeringRequest
    organization_id: uuid.UUID
    actor_user_id: uuid.UUID | None
    source_provider: Any | None = None
    validator: Any | None = None
    auto_fixer: Any | None = None
    healing_fix_generator: Any | None = None
    healing_result: dict | None = None
    materialization: Any | None = None
    handle: WorkspaceHandle | None = None
    code_plan: dict | None = None
    applier: Any | None = None
    rollback_snapshot: dict | None = None
    validation_run_id: uuid.UUID | None = None
    draft_pull_request_id: uuid.UUID | None = None
    stage_results: dict = field(default_factory=dict)


class ExecutionOrchestrator:
    def __init__(self, db: Session, *, workspace_manager: SecureWorkspaceManager | None = None) -> None:
        self.db = db
        self.audit = AuditService(db)
        self.workspace_manager = workspace_manager or SecureWorkspaceManager(db=db)

    # -- public API ------------------------------------------------------------

    def request_cancellation(
        self, *, engineering_request_id: uuid.UUID, organization_id: uuid.UUID
    ) -> ExecutionRun:
        run = self._get_run(engineering_request_id, organization_id)
        if run is None:
            raise NotFoundError("Execution run not found")
        run.cancellation_requested = True
        self.db.commit()
        self.db.refresh(run)
        return run

    def get_run(self, engineering_request_id: uuid.UUID, organization_id: uuid.UUID) -> ExecutionRun:
        run = self._get_run(engineering_request_id, organization_id)
        if run is None:
            raise NotFoundError("Execution run not found")
        return run

    def execute(
        self,
        *,
        engineering_request_id: uuid.UUID,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        source_provider: Any | None = None,
        validator: Any | None = None,
        auto_fixer: Any | None = None,
        healing_fix_generator: Any | None = None,
        timeout_seconds: float | None = None,
        now_fn: Callable[[], float] | None = None,
    ) -> ExecutionRun:
        request = self._require_request(engineering_request_id, organization_id)
        run = self._get_or_create_run(request, organization_id)

        # Idempotency: a completed run is returned unchanged.
        if run.status == TERMINAL_OK:
            return run

        if request.status != RequestStatus.APPROVED:
            self._fail(run, organization_id, actor_user_id, stage=None, error="request not approved")
            raise AppError("Execution requires an approved engineering request.")

        now = now_fn or time.monotonic
        deadline = (now() + timeout_seconds) if timeout_seconds is not None else None

        run.attempts += 1
        run.status = "running"
        self.db.commit()
        self._audit(organization_id, actor_user_id, "execution_started", run, {"attempt": run.attempts})
        logger.info("execution_started", extra={"execution_id": run.execution_id, "attempt": run.attempts})

        ctx = self._build_context(run, request, organization_id, actor_user_id, source_provider, validator, auto_fixer)
        ctx.healing_fix_generator = healing_fix_generator

        for stage in STAGES:
            # Cancellation between stages.
            self.db.refresh(run)
            if run.cancellation_requested:
                run.status = "cancelled"
                run.current_stage = stage
                self.db.commit()
                self._audit(organization_id, actor_user_id, "execution_cancelled", run, {"stage": stage})
                logger.info("execution_cancelled", extra={"execution_id": run.execution_id, "stage": stage})
                return run

            # Timeout between stages.
            if deadline is not None and now() > deadline:
                self._rollback_if_needed(ctx, run, organization_id, actor_user_id)
                self._fail(run, organization_id, actor_user_id, stage=stage, error="timeout")
                return run

            # Resume: skip stages already completed in a prior attempt.
            if stage in run.completed_stages:
                continue

            run.current_stage = stage
            self.db.commit()
            self._audit(organization_id, actor_user_id, "execution_progress", run, {"stage": stage})

            try:
                getattr(self, f"_run_{stage}")(ctx)
            except Exception as exc:  # noqa: BLE001
                self._rollback_if_needed(ctx, run, organization_id, actor_user_id)
                self._fail(run, organization_id, actor_user_id, stage=stage, error=str(exc)[:300])
                return run

            run.completed_stages = run.completed_stages + [stage]
            self._persist_stage(run, stage, ctx)
            self.db.commit()

        run.status = TERMINAL_OK
        run.current_stage = None
        run.report = self._report(run, ctx, success=True)
        self.db.commit()
        self._audit(organization_id, actor_user_id, "execution_completed", run, {"attempts": run.attempts})
        logger.info("execution_completed", extra={"execution_id": run.execution_id})
        self.db.refresh(run)
        return run

    # -- stage implementations (delegate to existing services) -----------------

    def _run_materialize(self, ctx: _Context) -> None:
        snapshot = RepositoryMaterializer(self.db, workspace_manager=self.workspace_manager).materialize(
            repository_id=ctx.request.repository_id,
            organization_id=ctx.organization_id,
            actor_user_id=ctx.actor_user_id,
            source_provider=ctx.source_provider,
        )
        if not snapshot.materialized:
            raise AppError(f"Repository could not be materialized: {snapshot.reason}")
        ctx.materialization = snapshot
        ctx.handle = self._handle_from(snapshot.workspace_path, snapshot.target_branch, snapshot.default_branch)

    def _run_generate(self, ctx: _Context) -> None:
        plan = CodeGenerationEngine(self.db).generate(
            engineering_request_id=ctx.request.id,
            organization_id=ctx.organization_id,
            actor_user_id=ctx.actor_user_id,
            materialization=ctx.materialization,
        )
        ctx.code_plan = plan.as_dict()

    def _run_apply(self, ctx: _Context) -> None:
        applier = SafeChangeApplier(
            workspace_manager=self.workspace_manager, handle=ctx.handle, db=self.db
        )
        result = applier.apply(
            (ctx.code_plan or {}).get("changes", []),
            dry_run=False,
            organization_id=ctx.organization_id,
            actor_user_id=ctx.actor_user_id,
        )
        ctx.applier = applier
        ctx.rollback_snapshot = result.rollback_snapshot

    def _run_validate(self, ctx: _Context) -> None:
        validator = ctx.validator
        # When no validator is injected, run REAL validation inside the workspace.
        if validator is None and ctx.handle is not None and ctx.handle.path:
            from app.services.agent.validation_runner import ValidationRunner, build_runner_validator

            runner = ValidationRunner(
                ctx.handle.path, db=self.db, organization_id=ctx.organization_id
            )
            validator = build_runner_validator(runner)

        run = ValidationService(self.db).run(
            engineering_request_id=ctx.request.id,
            organization_id=ctx.organization_id,
            actor_user_id=ctx.actor_user_id,
            validator=validator,
            auto_fixer=ctx.auto_fixer,
        )

        # On failure, attempt AI self-healing inside the workspace, then re-validate.
        if run.status != "passed" and ctx.handle is not None:
            from app.services.agent.self_healing_engine import SelfHealingEngine

            healing = SelfHealingEngine(self.db, workspace_manager=self.workspace_manager).heal(
                request=ctx.request,
                organization_id=ctx.organization_id,
                actor_user_id=ctx.actor_user_id,
                handle=ctx.handle,
                initial_checks=run.checks,
                validator=validator,
                repository_dna=getattr(ctx.materialization, "language_hints", None) and ctx.materialization,
                code_plan=ctx.code_plan,
                fix_generator=ctx.healing_fix_generator,
            )
            ctx.healing_result = healing.as_dict()
            if healing.status == "healed":
                run = ValidationService(self.db).run(
                    engineering_request_id=ctx.request.id,
                    organization_id=ctx.organization_id,
                    actor_user_id=ctx.actor_user_id,
                    validator=validator,
                    auto_fixer=ctx.auto_fixer,
                )

        if run.status != "passed":
            raise AppError("Validation failed; no draft pull request was created.")
        ctx.validation_run_id = run.id

    def _run_draft_pr(self, ctx: _Context) -> None:
        draft = DraftPullRequestService(self.db).get_for_request(ctx.request.id, ctx.organization_id)
        ctx.draft_pull_request_id = draft.id

    # -- state / helpers -------------------------------------------------------

    def _build_context(
        self, run, request, organization_id, actor_user_id, source_provider, validator, auto_fixer
    ) -> _Context:
        ctx = _Context(
            request=request,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            source_provider=source_provider,
            validator=validator,
            auto_fixer=auto_fixer,
        )
        # Reconstruct prior-stage outputs when resuming.
        if "materialize" in run.completed_stages and run.workspace_path:
            ctx.materialization = SimpleNamespace(
                materialized=True,
                workspace_path=run.workspace_path,
                target_branch=run.target_branch,
                default_branch=run.default_branch,
                language_hints=[],
            )
            ctx.handle = self._handle_from(run.workspace_path, run.target_branch, run.default_branch)
        if "generate" in run.completed_stages and run.code_plan:
            ctx.code_plan = run.code_plan
        if "apply" in run.completed_stages and run.rollback_snapshot:
            ctx.rollback_snapshot = run.rollback_snapshot
            if ctx.handle is not None:
                ctx.applier = SafeChangeApplier(
                    workspace_manager=self.workspace_manager, handle=ctx.handle, db=self.db
                )
        return ctx

    def _handle_from(self, path, target_branch, default_branch) -> WorkspaceHandle:
        return WorkspaceHandle(
            workspace_id="orchestrated",
            path=path,
            branch_name=target_branch,
            base_branch=default_branch,
            max_bytes=self.workspace_manager.max_bytes,
        )

    def _persist_stage(self, run: ExecutionRun, stage: str, ctx: _Context) -> None:
        if stage == "materialize" and ctx.materialization is not None:
            run.workspace_path = ctx.materialization.workspace_path
            run.target_branch = ctx.materialization.target_branch
            run.default_branch = ctx.materialization.default_branch
        elif stage == "generate":
            run.code_plan = ctx.code_plan or {}
        elif stage == "apply":
            run.rollback_snapshot = ctx.rollback_snapshot or {}
        elif stage == "validate":
            run.validation_run_id = ctx.validation_run_id
        elif stage == "draft_pr":
            run.draft_pull_request_id = ctx.draft_pull_request_id

    def _rollback_if_needed(self, ctx: _Context, run, organization_id, actor_user_id) -> None:
        if ctx.applier is not None and ctx.rollback_snapshot:
            try:
                ctx.applier.rollback(
                    ctx.rollback_snapshot, organization_id=organization_id, actor_user_id=actor_user_id
                )
            except Exception:  # noqa: BLE001 - best effort
                logger.warning("execution_rollback_error", extra={"execution_id": run.execution_id})
            run.report = {**(run.report or {}), "rolled_back": True}
            self._audit(organization_id, actor_user_id, "execution_rolled_back", run, {})
            logger.info("execution_rolled_back", extra={"execution_id": run.execution_id})

    def _fail(self, run, organization_id, actor_user_id, *, stage, error) -> None:
        run.status = "failed"
        run.current_stage = stage
        run.report = {**(run.report or {}), "error": error, "failed_stage": stage}
        self.db.commit()
        self._audit(organization_id, actor_user_id, "execution_failed", run, {"stage": stage, "error": error})
        logger.warning("execution_failed", extra={"execution_id": run.execution_id, "stage": stage, "error": error})

    def _report(self, run: ExecutionRun, ctx: _Context, *, success: bool) -> dict:
        return {
            "success": success,
            "attempts": run.attempts,
            "completed_stages": list(run.completed_stages),
            "draft_pull_request_id": str(run.draft_pull_request_id) if run.draft_pull_request_id else None,
            "validation_run_id": str(run.validation_run_id) if run.validation_run_id else None,
            "workspace_path": run.workspace_path,
            "healing": ctx.healing_result,
        }

    def _get_or_create_run(self, request: EngineeringRequest, organization_id: uuid.UUID) -> ExecutionRun:
        run = self._get_run(request.id, organization_id)
        if run is None:
            run = ExecutionRun(
                organization_id=organization_id,
                engineering_request_id=request.id,
                execution_id=f"exec-{request.id.hex}",
                status="pending",
                completed_stages=[],
                code_plan={},
                rollback_snapshot={},
                report={},
            )
            self.db.add(run)
            self.db.commit()
            self.db.refresh(run)
        return run

    def _get_run(self, engineering_request_id: uuid.UUID, organization_id: uuid.UUID) -> ExecutionRun | None:
        return self.db.scalar(
            select(ExecutionRun).where(
                ExecutionRun.engineering_request_id == engineering_request_id,
                ExecutionRun.organization_id == organization_id,
            )
        )

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

    def _audit(self, organization_id, actor_user_id, action, run: ExecutionRun, metadata: dict) -> None:
        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type="execution_run",
            target_id=run.execution_id,
            metadata=metadata,
        )
