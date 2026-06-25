from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from app.core.errors import AppError, NotFoundError
from app.models.audit import AuditLog
from app.models.draft_pull_request import DraftPullRequest
from app.models.execution_run import ExecutionRun
from app.services.agent.github_draft_pr_creator import GitHubDraftPRCreator
from app.services.engineering_planning_service import EngineeringPlanningService

BASE = "/api/v1/engineering-requests"


class FakeClient:
    def __init__(self) -> None:
        self.pushed = None
        self.pr = None

    def push_branch(self, **kwargs):
        self.pushed = kwargs
        return {"branch": kwargs["branch"], "base_sha": "base123"}

    def open_draft_pull_request(self, **kwargs):
        self.pr = kwargs
        return {"number": 42, "html_url": "https://github.com/acme-labs/payments-api/pull/42"}


def _approved_request(api_context, monkeypatch, *, connect: bool = True) -> str:
    plan_payload = {
        "summary": "ok",
        "affected_files": [{"path": "src/feature.py", "reason": "x"}],
        "implementation_plan": ["do it"],
        "test_plan": ["test"],
        "risk_level": "low",
        "safety_notes": [],
    }
    monkeypatch.setattr(EngineeringPlanningService, "_call_ai", lambda self, prompt: json.dumps(plan_payload))
    created = api_context.client.post(
        BASE,
        json={
            "title": "Add feature",
            "description": "desc",
            "request_type": "feature",
            "repository_id": str(api_context.repository.id),
        },
    ).json()
    api_context.client.post(f"{BASE}/{created['id']}/analyze")
    api_context.client.post(f"{BASE}/{created['id']}/approve-plan")
    if connect:
        api_context.repository.github_installation_id = _make_installation(api_context)
        api_context.db.commit()
    return created["id"]


def _make_installation(api_context):
    from app.models.github import GitHubInstallation

    inst = GitHubInstallation(
        organization_id=api_context.organization.id,
        installation_id=556677,
        account_login="acme-labs",
        account_type="Organization",
        permissions={},
    )
    api_context.db.add(inst)
    api_context.db.flush()
    return inst.id


def _draft_and_run(
    api_context,
    request_id: str,
    *,
    branch="codedna/ai/feature-abc",
    base="main",
    run_status="completed",
    workspace: Path | None = None,
    files_to_create=None,
) -> tuple[DraftPullRequest, ExecutionRun]:
    draft = DraftPullRequest(
        organization_id=api_context.organization.id,
        engineering_request_id=uuid.UUID(request_id),
        repository_id=api_context.repository.id,
        branch_name=branch,
        base_branch=base,
        title="[CodeDNA AI] Add feature",
        body="## Plan",
        commit_plan=[{"order": 1, "message": "feat: add feature", "files": []}],
        labels=["codedna-ai"],
        status="draft",
        is_pushed=False,
        human_approval_required=True,
    )
    run = ExecutionRun(
        organization_id=api_context.organization.id,
        engineering_request_id=uuid.UUID(request_id),
        execution_id=f"exec-{uuid.UUID(request_id).hex}",
        status=run_status,
        completed_stages=["materialize", "generate", "apply", "validate"],
        workspace_path=str(workspace) if workspace else None,
        code_plan={"files_to_modify": [], "files_to_create": files_to_create or [], "files_to_delete": []},
        report={"healing": None},
    )
    api_context.db.add_all([draft, run])
    api_context.db.commit()
    return draft, run


def test_creates_draft_pr_with_mocked_github(api_context, monkeypatch, tmp_path) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "src").mkdir()
    (ws / "src/feature.py").write_text("x = 1\n")
    _draft_and_run(api_context, request_id, workspace=ws, files_to_create=["src/feature.py"])

    client = FakeClient()
    draft = GitHubDraftPRCreator(api_context.db, client=client).create(
        engineering_request_id=uuid.UUID(request_id),
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    assert draft.is_pushed is True
    assert draft.status == "open"
    assert draft.github_pr_number == 42
    assert "pull/42" in draft.github_pr_url
    assert client.pushed["branch"] == "codedna/ai/feature-abc"
    assert ("src/feature.py", "x = 1\n") in client.pushed["files"]
    assert "Human review required" in draft.body

    actions = {r.action for r in api_context.db.query(AuditLog).filter(AuditLog.target_id == request_id).all()}
    assert {"draft_pr_creation_started", "draft_pr_branch_pushed", "draft_pr_created"} <= actions


def test_refuses_default_branch(api_context, monkeypatch, tmp_path) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    _draft_and_run(api_context, request_id, branch="main", base="main", workspace=tmp_path)
    with pytest.raises(AppError):
        GitHubDraftPRCreator(api_context.db, client=FakeClient()).create(
            engineering_request_id=uuid.UUID(request_id),
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
        )


def test_refuses_failed_validation(api_context, monkeypatch, tmp_path) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    _draft_and_run(api_context, request_id, run_status="failed", workspace=tmp_path)
    with pytest.raises(AppError):
        GitHubDraftPRCreator(api_context.db, client=FakeClient()).create(
            engineering_request_id=uuid.UUID(request_id),
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
        )


def test_refuses_forbidden_files(api_context, monkeypatch, tmp_path) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / ".env").write_text("SECRET=1")
    _draft_and_run(api_context, request_id, workspace=ws, files_to_create=[".env"])
    with pytest.raises(AppError):
        GitHubDraftPRCreator(api_context.db, client=FakeClient()).create(
            engineering_request_id=uuid.UUID(request_id),
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
        )


def test_refuses_missing_installation(api_context, monkeypatch, tmp_path) -> None:
    request_id = _approved_request(api_context, monkeypatch, connect=False)  # not connected
    _draft_and_run(api_context, request_id, workspace=tmp_path)
    with pytest.raises(AppError):
        GitHubDraftPRCreator(api_context.db, client=FakeClient()).create(
            engineering_request_id=uuid.UUID(request_id),
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
        )


def test_idempotent_duplicate_prevention(api_context, monkeypatch, tmp_path) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    ws = tmp_path / "ws"
    ws.mkdir()
    _draft_and_run(api_context, request_id, workspace=ws)

    creator = GitHubDraftPRCreator(api_context.db, client=FakeClient())
    first = creator.create(
        engineering_request_id=uuid.UUID(request_id),
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    second_client = FakeClient()
    second = GitHubDraftPRCreator(api_context.db, client=second_client).create(
        engineering_request_id=uuid.UUID(request_id),
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    assert first.github_pr_url == second.github_pr_url
    assert second_client.pushed is None  # no second push


def test_org_isolation(api_context, tmp_path) -> None:
    other_id = str(uuid.uuid4())
    with pytest.raises(NotFoundError):
        GitHubDraftPRCreator(api_context.db, client=FakeClient()).create(
            engineering_request_id=uuid.UUID(other_id),
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
        )
