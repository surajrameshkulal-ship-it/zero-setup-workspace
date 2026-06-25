from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.core.config import settings
from app.core.errors import NotFoundError
from app.models.engineering_request import (
    EngineeringRequest,
    RequestPriority,
    RequestStatus,
    RequestType,
)
from app.services.agent.self_healing_engine import SelfHealingEngine
from app.services.workspace.secure_workspace_manager import SecureWorkspaceManager


def _request(api_context, *, org=None) -> EngineeringRequest:
    req = EngineeringRequest(
        organization_id=(org or api_context.organization).id,
        title="Heal me",
        description="fix the build",
        request_type=RequestType.BUG,
        priority=RequestPriority.MEDIUM,
        status=RequestStatus.APPROVED,
        affected_files=[],
        implementation_plan=[],
        test_plan=[],
        safety_notes={},
    )
    api_context.db.add(req)
    api_context.db.commit()
    return req


def _engine_and_handle(api_context, tmp_path):
    mgr = SecureWorkspaceManager(db=api_context.db, base_dir=tmp_path / "ws")
    handle = mgr.create_workspace(branch_name="codedna/ai/heal-x", base_branch="main")
    engine = SelfHealingEngine(api_context.db, workspace_manager=mgr)
    return engine, handle, Path(handle.path)


FAILING = [{"name": "pytest", "status": "failed", "details": "1 failed"}]


def _validator_sequence(*sequences):
    """Return a validator that yields the given check-lists on successive calls."""
    calls = {"i": 0}

    def validator(context, attempt):
        idx = min(calls["i"], len(sequences) - 1)
        calls["i"] += 1
        return sequences[idx]

    return validator


def _fix(content="patched\n", path="src/app.py"):
    def gen(failures, context):
        return [{"path": path, "operations": [{"type": "create_file", "content": content}]}]
    return gen


def test_single_pass_healing(api_context, tmp_path) -> None:
    engine, handle, ws = _engine_and_handle(api_context, tmp_path)
    request = _request(api_context)
    validator = _validator_sequence([{"name": "pytest", "status": "passed", "details": "ok"}])

    result = engine.heal(
        request=request,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        handle=handle,
        initial_checks=FAILING,
        validator=validator,
        fix_generator=_fix(),
    )
    assert result.status == "healed"
    assert len(result.iterations) == 1
    assert result.fixes_applied >= 1
    assert (ws / "src/app.py").read_text() == "patched\n"  # workspace modified


def test_multi_pass_healing(api_context, tmp_path) -> None:
    engine, handle, _ws = _engine_and_handle(api_context, tmp_path)
    request = _request(api_context)
    # fail after first fix, pass after second
    validator = _validator_sequence(
        [{"name": "pytest", "status": "failed", "details": "still failing"}],
        [{"name": "pytest", "status": "passed", "details": "ok"}],
    )
    result = engine.heal(
        request=request,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        handle=handle,
        initial_checks=FAILING,
        validator=validator,
        fix_generator=_fix(),
        max_retries=3,
    )
    assert result.status == "healed"
    assert len(result.iterations) == 2


def test_retry_limit_reached_rolls_back(api_context, tmp_path) -> None:
    engine, handle, ws = _engine_and_handle(api_context, tmp_path)
    request = _request(api_context)
    always_fail = _validator_sequence([{"name": "pytest", "status": "failed", "details": "nope"}])

    result = engine.heal(
        request=request,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        handle=handle,
        initial_checks=FAILING,
        validator=always_fail,
        fix_generator=_fix(path="src/created.py"),
        max_retries=2,
    )
    assert result.status == "retry_limit"
    assert result.rolled_back is True
    assert "pytest" in result.remaining_failures
    # All created files were rolled back.
    assert not (ws / "src/created.py").exists()


def test_protected_file_rejection_rolls_back(api_context, tmp_path) -> None:
    engine, handle, ws = _engine_and_handle(api_context, tmp_path)
    request = _request(api_context)
    validator = _validator_sequence([{"name": "pytest", "status": "passed"}])

    result = engine.heal(
        request=request,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        handle=handle,
        initial_checks=FAILING,
        validator=validator,
        fix_generator=_fix(path=".env"),  # forbidden
    )
    assert result.status == "failed"
    assert "safety" in (result.reason or "").lower() or "rejected" in (result.reason or "").lower()
    assert not (ws / ".env").exists()


def test_provider_unavailable(api_context, tmp_path, monkeypatch) -> None:
    engine, handle, _ws = _engine_and_handle(api_context, tmp_path)
    request = _request(api_context)
    monkeypatch.setattr(settings, "ai_review_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", None)  # router will raise

    result = engine.heal(
        request=request,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        handle=handle,
        initial_checks=FAILING,
        validator=_validator_sequence([{"name": "pytest", "status": "failed"}]),
        # no fix_generator -> uses the AI router
    )
    assert result.status == "failed"
    assert "unavailable" in (result.reason or "").lower()


def test_no_failures_returns_healed(api_context, tmp_path) -> None:
    engine, handle, _ws = _engine_and_handle(api_context, tmp_path)
    request = _request(api_context)
    result = engine.heal(
        request=request,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        handle=handle,
        initial_checks=[{"name": "pytest", "status": "passed"}],
        validator=_validator_sequence([{"name": "pytest", "status": "passed"}]),
        fix_generator=_fix(),
    )
    assert result.status == "healed"
    assert result.iterations == []


def test_org_isolation(api_context, tmp_path) -> None:
    engine, handle, _ws = _engine_and_handle(api_context, tmp_path)
    foreign = _request(api_context, org=api_context.other_organization)
    with pytest.raises(NotFoundError):
        engine.heal(
            request=foreign,
            organization_id=api_context.organization.id,  # mismatched org
            actor_user_id=api_context.user.id,
            handle=handle,
            initial_checks=FAILING,
            validator=_validator_sequence([{"name": "pytest", "status": "passed"}]),
            fix_generator=_fix(),
        )
