from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from app.core.errors import AppError, NotFoundError
from app.models.audit import AuditLog
from app.models.engineering_request import (
    EngineeringRequest,
    RequestPriority,
    RequestStatus,
    RequestType,
)
from app.models.execution_run import ExecutionRun
from app.services.agent.code_generation_engine import CodeGenerationEngine
from app.services.agent.execution_orchestrator import STAGES, ExecutionOrchestrator
from app.services.engineering_planning_service import EngineeringPlanningService
from app.services.workspace.secure_workspace_manager import SecureWorkspaceManager

BASE = "/api/v1/engineering-requests"


def _orchestrator(api_context, tmp_path) -> ExecutionOrchestrator:
    mgr = SecureWorkspaceManager(db=api_context.db, base_dir=tmp_path / "ws")
    return ExecutionOrchestrator(api_context.db, workspace_manager=mgr)


def _approved_request(api_context, monkeypatch, *, connect: bool = False) -> EngineeringRequest:
    plan_payload = {
        "summary": "ok",
        "affected_files": [{"path": "src/feature.py", "reason": "x"}],
        "implementation_plan": ["do it"],
        "test_plan": ["test"],
        "risk_level": "low",
        "safety_notes": [],
    }
    monkeypatch.setattr(
        EngineeringPlanningService, "_call_ai", lambda self, prompt: json.dumps(plan_payload)
    )
    created = api_context.client.post(
        BASE,
        json={
            "title": "Add feature",
            "description": "Add a feature.",
            "request_type": "feature",
            "repository_id": str(api_context.repository.id),
        },
    ).json()
    api_context.client.post(f"{BASE}/{created['id']}/analyze")
    api_context.client.post(f"{BASE}/{created['id']}/approve-plan")
    if connect:
        api_context.repository.github_installation_id = uuid.uuid4()
        api_context.db.commit()
    return api_context.db.get(EngineeringRequest, uuid.UUID(created["id"]))


def _audit_actions(api_context, target_id: str) -> set[str]:
    api_context.db.flush()
    return {
        row.action
        for row in api_context.db.query(AuditLog).filter(AuditLog.target_id == target_id).all()
    }


# -- successful end-to-end (real services) -------------------------------------


def test_successful_end_to_end(api_context, monkeypatch, tmp_path) -> None:
    request = _approved_request(api_context, monkeypatch, connect=True)
    orch = _orchestrator(api_context, tmp_path)

    def source_provider(repo, dest):
        (Path(dest) / "README.md").write_text("# demo\n")
        return {"commit_sha": "deadbee"}

    monkeypatch.setattr(
        CodeGenerationEngine,
        "_call_ai",
        lambda self, prompt: json.dumps(
            {
                "changes": [
                    {
                        "path": "src/feature.py",
                        "operation": "create",
                        "language": "Python",
                        "operations": [{"type": "create_file", "content": "x = 1\n", "explanation": "new"}],
                        "explanation": "add feature",
                    }
                ],
                "tests_to_add": ["t"],
                "documentation_updates": ["d"],
                "estimated_lines_changed": 1,
                "confidence_score": 0.9,
            }
        ),
    )
    all_pass = lambda ctx, attempt: [{"name": "pytest", "status": "passed", "details": "ok"}]  # noqa: E731

    run = orch.execute(
        engineering_request_id=request.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        source_provider=source_provider,
        validator=all_pass,
    )

    assert run.status == "completed"
    assert run.completed_stages == list(STAGES)
    assert run.draft_pull_request_id is not None
    # The change was applied INSIDE the workspace only.
    assert (Path(run.workspace_path) / "src/feature.py").read_text() == "x = 1\n"

    actions = _audit_actions(api_context, run.execution_id)
    assert "execution_started" in actions
    assert "execution_progress" in actions
    assert "execution_completed" in actions


# -- failure at every stage ----------------------------------------------------


@pytest.mark.parametrize("failing_stage", list(STAGES))
def test_failure_at_each_stage(api_context, monkeypatch, tmp_path, failing_stage) -> None:
    request = _approved_request(api_context, monkeypatch)
    orch = _orchestrator(api_context, tmp_path)

    for stage in STAGES:
        monkeypatch.setattr(ExecutionOrchestrator, f"_run_{stage}", lambda self, ctx: None)

    def boom(self, ctx):
        raise RuntimeError("stage exploded")

    monkeypatch.setattr(ExecutionOrchestrator, f"_run_{failing_stage}", boom)

    run = orch.execute(
        engineering_request_id=request.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    assert run.status == "failed"
    assert run.current_stage == failing_stage
    assert failing_stage not in run.completed_stages
    earlier = STAGES[: STAGES.index(failing_stage)]
    assert all(s in run.completed_stages for s in earlier)
    assert "execution_failed" in _audit_actions(api_context, run.execution_id)


# -- rollback ------------------------------------------------------------------


def test_rollback_on_failure_after_apply(api_context, monkeypatch, tmp_path) -> None:
    request = _approved_request(api_context, monkeypatch)
    orch = _orchestrator(api_context, tmp_path)

    rolled = {"called": False}

    class FakeApplier:
        def rollback(self, snapshot, **kwargs):
            rolled["called"] = True
            return list(snapshot.keys())

    monkeypatch.setattr(ExecutionOrchestrator, "_run_materialize", lambda self, ctx: None)
    monkeypatch.setattr(ExecutionOrchestrator, "_run_generate", lambda self, ctx: None)

    def run_apply(self, ctx):
        ctx.applier = FakeApplier()
        ctx.rollback_snapshot = {"src/x.py": {"existed": False, "content_b64": None}}

    monkeypatch.setattr(ExecutionOrchestrator, "_run_apply", run_apply)

    def fail_validate(self, ctx):
        raise RuntimeError("validation blew up")

    monkeypatch.setattr(ExecutionOrchestrator, "_run_validate", fail_validate)
    monkeypatch.setattr(ExecutionOrchestrator, "_run_draft_pr", lambda self, ctx: None)

    run = orch.execute(
        engineering_request_id=request.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    assert run.status == "failed"
    assert run.current_stage == "validate"
    assert rolled["called"] is True
    assert run.report.get("rolled_back") is True
    assert "execution_rolled_back" in _audit_actions(api_context, run.execution_id)


# -- retry / resume ------------------------------------------------------------


def test_retry_resumes_completed_stages(api_context, monkeypatch, tmp_path) -> None:
    request = _approved_request(api_context, monkeypatch)
    orch = _orchestrator(api_context, tmp_path)

    counts = {s: 0 for s in STAGES}

    def make_counter(stage):
        def fn(self, ctx):
            counts[stage] += 1
        return fn

    for stage in ("materialize", "generate", "validate", "draft_pr"):
        monkeypatch.setattr(ExecutionOrchestrator, f"_run_{stage}", make_counter(stage))

    apply_state = {"fail": True}

    def run_apply(self, ctx):
        counts["apply"] += 1
        if apply_state["fail"]:
            raise RuntimeError("apply failed once")

    monkeypatch.setattr(ExecutionOrchestrator, "_run_apply", run_apply)

    first = orch.execute(
        engineering_request_id=request.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    assert first.status == "failed"
    assert first.completed_stages == ["materialize", "generate"]

    apply_state["fail"] = False
    second = orch.execute(
        engineering_request_id=request.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    assert second.status == "completed"
    assert second.id == first.id  # same deterministic run
    # Completed stages were not re-run on resume.
    assert counts["materialize"] == 1
    assert counts["generate"] == 1
    assert counts["apply"] == 2  # failed once, succeeded once
    assert second.attempts == 2


# -- cancellation --------------------------------------------------------------


def test_cancellation(api_context, monkeypatch, tmp_path) -> None:
    request = _approved_request(api_context, monkeypatch)
    orch = _orchestrator(api_context, tmp_path)

    # Pre-create the run with cancellation already requested.
    run = ExecutionRun(
        organization_id=api_context.organization.id,
        engineering_request_id=request.id,
        execution_id=f"exec-{request.id.hex}",
        status="pending",
        completed_stages=[],
        cancellation_requested=True,
        code_plan={},
        rollback_snapshot={},
        report={},
    )
    api_context.db.add(run)
    api_context.db.commit()

    for stage in STAGES:
        monkeypatch.setattr(ExecutionOrchestrator, f"_run_{stage}", lambda self, ctx: None)

    result = orch.execute(
        engineering_request_id=request.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    assert result.status == "cancelled"
    assert result.completed_stages == []
    assert "execution_cancelled" in _audit_actions(api_context, result.execution_id)


# -- timeout -------------------------------------------------------------------


def test_timeout(api_context, monkeypatch, tmp_path) -> None:
    request = _approved_request(api_context, monkeypatch)
    orch = _orchestrator(api_context, tmp_path)
    for stage in STAGES:
        monkeypatch.setattr(ExecutionOrchestrator, f"_run_{stage}", lambda self, ctx: None)

    # now() calls: deadline(0), materialize check(0, ok), generate check(100, > 5).
    values = iter([0, 0, 100])
    now_fn = lambda: next(values, 1000)  # noqa: E731

    run = orch.execute(
        engineering_request_id=request.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        timeout_seconds=5,
        now_fn=now_fn,
    )
    assert run.status == "failed"
    assert run.report.get("error") == "timeout"
    assert "materialize" in run.completed_stages
    assert run.current_stage == "generate"


# -- org isolation -------------------------------------------------------------


def test_org_isolation(api_context, tmp_path) -> None:
    foreign = EngineeringRequest(
        organization_id=api_context.other_organization.id,
        title="Foreign",
        description="other tenant",
        request_type=RequestType.FEATURE,
        priority=RequestPriority.MEDIUM,
        status=RequestStatus.APPROVED,
        affected_files=[],
        implementation_plan=[],
        test_plan=[],
        safety_notes={},
    )
    api_context.db.add(foreign)
    api_context.db.commit()
    orch = _orchestrator(api_context, tmp_path)
    with pytest.raises(NotFoundError):
        orch.execute(
            engineering_request_id=foreign.id,
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
        )


# -- idempotency ---------------------------------------------------------------


def test_idempotent_completed_run(api_context, monkeypatch, tmp_path) -> None:
    request = _approved_request(api_context, monkeypatch)
    orch = _orchestrator(api_context, tmp_path)

    counts = {"materialize": 0}

    def materialize(self, ctx):
        counts["materialize"] += 1

    monkeypatch.setattr(ExecutionOrchestrator, "_run_materialize", materialize)
    for stage in ("generate", "apply", "validate", "draft_pr"):
        monkeypatch.setattr(ExecutionOrchestrator, f"_run_{stage}", lambda self, ctx: None)

    first = orch.execute(
        engineering_request_id=request.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    assert first.status == "completed"

    second = orch.execute(
        engineering_request_id=request.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    assert second.id == first.id
    assert second.status == "completed"
    assert counts["materialize"] == 1  # not re-run after completion
    assert second.attempts == 1


def test_orchestrator_uses_real_validation_runner(api_context, monkeypatch, tmp_path) -> None:
    from types import SimpleNamespace

    from app.services.agent import validation_runner as vr_module
    from app.services.agent.validation_runner import CommandResult, ValidationRunner

    request = _approved_request(api_context, monkeypatch, connect=True)
    orch = _orchestrator(api_context, tmp_path)

    workdir = tmp_path / "real-ws"
    workdir.mkdir()

    def fake_materialize(self, ctx):
        ctx.materialization = SimpleNamespace(
            materialized=True,
            workspace_path=str(workdir),
            target_branch="codedna/ai/feature-x",
            default_branch="main",
            language_hints=[],
        )
        ctx.handle = self._handle_from(str(workdir), "codedna/ai/feature-x", "main")

    monkeypatch.setattr(ExecutionOrchestrator, "_run_materialize", fake_materialize)
    monkeypatch.setattr(ExecutionOrchestrator, "_run_generate", lambda self, ctx: None)
    monkeypatch.setattr(ExecutionOrchestrator, "_run_apply", lambda self, ctx: None)

    called = {"runner": False}

    def fake_run(self, commands=None):
        called["runner"] = True
        return [CommandResult("pytest", "python -m pytest", "passed", 0, 1.0, "", "", None)]

    monkeypatch.setattr(ValidationRunner, "run", fake_run)

    run = orch.execute(
        engineering_request_id=request.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        # No validator injected -> orchestrator must build the real ValidationRunner.
    )
    assert called["runner"] is True
    assert run.status == "completed"
    assert run.draft_pull_request_id is not None


def test_orchestrator_self_heals_then_drafts_pr(api_context, monkeypatch, tmp_path) -> None:
    from types import SimpleNamespace

    request = _approved_request(api_context, monkeypatch, connect=True)
    orch = _orchestrator(api_context, tmp_path)

    workdir = tmp_path / "heal-ws"
    workdir.mkdir()

    def fake_materialize(self, ctx):
        ctx.materialization = SimpleNamespace(
            materialized=True,
            workspace_path=str(workdir),
            target_branch="codedna/ai/feature-x",
            default_branch="main",
            language_hints=["Python"],
        )
        ctx.handle = self._handle_from(str(workdir), "codedna/ai/feature-x", "main")

    monkeypatch.setattr(ExecutionOrchestrator, "_run_materialize", fake_materialize)
    monkeypatch.setattr(ExecutionOrchestrator, "_run_generate", lambda self, ctx: None)
    monkeypatch.setattr(ExecutionOrchestrator, "_run_apply", lambda self, ctx: None)

    # Validation fails on the first call, passes afterward (after healing applies a fix).
    seq = {"i": 0}

    def validator(context, attempt):
        seq["i"] += 1
        status = "failed" if seq["i"] == 1 else "passed"
        return [{"name": "pytest", "status": status, "details": "x"}]

    def fix_gen(failures, context):
        return [{"path": "src/fix.py", "operations": [{"type": "create_file", "content": "ok\n"}]}]

    run = orch.execute(
        engineering_request_id=request.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        validator=validator,
        healing_fix_generator=fix_gen,
    )
    assert run.status == "completed"
    assert run.draft_pull_request_id is not None
    assert run.report["healing"]["status"] == "healed"
    assert (workdir / "src/fix.py").read_text() == "ok\n"


def test_requires_approved_request(api_context, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(EngineeringPlanningService, "_call_ai", lambda self, prompt: None)
    created = api_context.client.post(
        BASE, json={"title": "Pending request", "description": "x", "request_type": "bug"}
    ).json()
    api_context.client.post(f"{BASE}/{created['id']}/analyze")  # plan_ready, not approved
    orch = _orchestrator(api_context, tmp_path)
    with pytest.raises(AppError):
        orch.execute(
            engineering_request_id=uuid.UUID(created["id"]),
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
        )
