from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from app.core.errors import AppError
from app.services.agent.code_generation_engine import CodeGenerationEngine
from app.services.agent.safe_change_applier import SafeChangeApplier, normalize_operation_type
from app.services.engineering_planning_service import EngineeringPlanningService
from app.services.workspace.secure_workspace_manager import SecureWorkspaceManager

BASE = "/api/v1/engineering-requests"


def _setup(tmp_path, initial: dict[str, str] | None = None):
    mgr = SecureWorkspaceManager(base_dir=tmp_path / "ws")
    handle = mgr.create_workspace(branch_name="codedna/ai/feature-x", base_branch="main")
    ws = Path(handle.path)
    for rel, content in (initial or {}).items():
        target = ws / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return SafeChangeApplier(workspace_manager=mgr, handle=handle), ws


def test_normalize_operation_type() -> None:
    assert normalize_operation_type("create", has_target=False) == "create_file"
    assert normalize_operation_type("modify", has_target=False) == "replace_file"
    assert normalize_operation_type("modify", has_target=True) == "replace_block"
    assert normalize_operation_type("update", has_target=False) == "replace_file"
    assert normalize_operation_type("delete", has_target=False) == "delete_file"
    assert normalize_operation_type("insert", has_target=False) == "insert_after"
    assert normalize_operation_type("create_file", has_target=False) == "create_file"
    assert normalize_operation_type("frobnicate", has_target=False) == "frobnicate"


def test_generic_create_operation_applies(tmp_path) -> None:
    applier, ws = _setup(tmp_path)
    changes = [{"path": "src/x.py", "operations": [{"type": "create", "content": "x = 1\n"}]}]
    result = applier.apply(changes, dry_run=False)
    assert result.files_changed == ["src/x.py"]
    assert (ws / "src/x.py").read_text() == "x = 1\n"


def test_generic_modify_full_content_applies(tmp_path) -> None:
    applier, ws = _setup(tmp_path, {"a.py": "old\n"})
    changes = [{"path": "a.py", "operations": [{"type": "modify", "content": "new content\n"}]}]
    result = applier.apply(changes, dry_run=False)
    assert "a.py" in result.files_changed
    assert (ws / "a.py").read_text() == "new content\n"


def test_generic_modify_with_target_is_in_place(tmp_path) -> None:
    applier, ws = _setup(tmp_path, {"a.py": "line1\nOLD\nline2\n"})
    changes = [{"path": "a.py", "operations": [{"type": "modify", "target": "OLD", "content": "NEW"}]}]
    applier.apply(changes, dry_run=False)
    assert (ws / "a.py").read_text() == "line1\nNEW\nline2\n"


def test_empty_content_does_not_clobber(tmp_path) -> None:
    applier, ws = _setup(tmp_path, {"a.py": "keep me\n"})
    changes = [{"path": "a.py", "operations": [{"type": "modify", "content": ""}]}]
    result = applier.apply(changes, dry_run=False)
    assert result.files_changed == []  # nothing applied
    assert any(s["reason"] == "empty content" for s in result.skipped_operations)
    assert (ws / "a.py").read_text() == "keep me\n"  # file preserved


def test_unsupported_operation_skipped_clearly(tmp_path) -> None:
    applier, ws = _setup(tmp_path, {"a.py": "x\n"})
    changes = [{"path": "a.py", "operations": [{"type": "frobnicate", "content": "?"}]}]
    result = applier.apply(changes, dry_run=False)
    assert result.files_changed == []
    assert any(s["reason"] == "unsupported operation" for s in result.skipped_operations)


def test_engine_output_applies_through_applier(api_context, monkeypatch, tmp_path) -> None:
    # An approved request + a CodeGenerationEngine plan using a generic 'modify'
    # operation with full content must apply to a real workspace.
    plan_payload = {
        "summary": "ok",
        "affected_files": [{"path": "src/feature.py", "reason": "x"}],
        "implementation_plan": ["do it"],
        "test_plan": ["t"],
        "risk_level": "low",
        "safety_notes": [],
    }
    monkeypatch.setattr(EngineeringPlanningService, "_call_ai", lambda self, prompt: json.dumps(plan_payload))
    created = api_context.client.post(
        BASE,
        json={
            "title": "Add feature",
            "description": "d",
            "request_type": "feature",
            "repository_id": str(api_context.repository.id),
        },
    ).json()
    api_context.client.post(f"{BASE}/{created['id']}/analyze")
    api_context.client.post(f"{BASE}/{created['id']}/approve-plan")

    monkeypatch.setattr(
        CodeGenerationEngine,
        "_call_ai",
        lambda self, prompt: json.dumps(
            {
                "changes": [
                    {
                        "path": "src/feature.py",
                        "operation": "create",
                        "operations": [{"type": "create_file", "content": "DARK_MODE = True\n"}],
                        "explanation": "add dark mode flag",
                    }
                ],
                "confidence_score": 0.9,
            }
        ),
    )
    from types import SimpleNamespace

    mgr = SecureWorkspaceManager(base_dir=tmp_path / "ws")
    handle = mgr.create_workspace(branch_name="codedna/ai/feature-x", base_branch="main")
    materialization = SimpleNamespace(
        materialized=True,
        workspace_path=handle.path,
        target_branch="codedna/ai/feature-x",
        default_branch="main",
        language_hints=["Python"],
    )
    plan = CodeGenerationEngine(api_context.db).generate(
        engineering_request_id=uuid.UUID(created["id"]),
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        materialization=materialization,
    )
    applier = SafeChangeApplier(workspace_manager=mgr, handle=handle)
    result = applier.apply(plan.changes, dry_run=False)
    assert result.files_changed == ["src/feature.py"]
    assert (Path(handle.path) / "src/feature.py").read_text() == "DARK_MODE = True\n"


def test_create_draft_pr_surfaces_no_change_error(api_context, monkeypatch) -> None:
    # If the change builder yields nothing, create() returns the exact reason.
    from app.models.draft_pull_request import DraftPullRequest
    from app.models.github import GitHubInstallation
    from app.models.validation_run import ValidationRun
    from app.services.agent.github_draft_pr_creator import GitHubDraftPRCreator

    plan_payload = {"summary": "ok", "affected_files": [], "implementation_plan": ["x"], "test_plan": ["t"], "risk_level": "low", "safety_notes": []}
    monkeypatch.setattr(EngineeringPlanningService, "_call_ai", lambda self, prompt: json.dumps(plan_payload))
    created = api_context.client.post(
        BASE, json={"title": "No changes", "description": "d", "request_type": "feature", "repository_id": str(api_context.repository.id)}
    ).json()
    api_context.client.post(f"{BASE}/{created['id']}/analyze")
    api_context.client.post(f"{BASE}/{created['id']}/approve-plan")

    inst = GitHubInstallation(
        organization_id=api_context.organization.id, installation_id=42, account_login="acme-labs", account_type="Organization", permissions={}
    )
    api_context.db.add(inst)
    api_context.db.flush()
    api_context.repository.github_installation_id = inst.id
    api_context.db.add(
        DraftPullRequest(
            organization_id=api_context.organization.id,
            engineering_request_id=uuid.UUID(created["id"]),
            repository_id=api_context.repository.id,
            branch_name="codedna/ai/feature-x",
            base_branch="main",
            title="[CodeDNA AI] No changes",
            body="b",
            commit_plan=[{"order": 1, "message": "x", "files": []}],
            labels=["codedna-ai"],
        )
    )
    api_context.db.add(
        ValidationRun(
            organization_id=api_context.organization.id,
            engineering_request_id=uuid.UUID(created["id"]),
            status="passed",
            checks=[{"name": "pytest", "status": "passed"}],
            report={"success": True, "passed": ["pytest"]},
        )
    )
    api_context.db.commit()

    creator = GitHubDraftPRCreator(
        api_context.db,
        client=object(),  # never reached
        change_builder=lambda **kw: ([], []),  # zero-change plan
    )
    with pytest.raises(AppError) as exc:
        creator.create(
            engineering_request_id=uuid.UUID(created["id"]),
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
        )
    assert "no changes were applied from code generation plan" in str(exc.value).lower()
