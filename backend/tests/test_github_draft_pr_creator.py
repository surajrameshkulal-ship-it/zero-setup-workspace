from __future__ import annotations

import json
import uuid

import pytest

from app.core.errors import AppError, NotFoundError
from app.models.audit import AuditLog
from app.models.draft_pull_request import DraftPullRequest
from app.models.github import GitHubInstallation
from app.models.validation_run import ValidationRun
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


def _builder(files, deletions=None):
    def build(*, request, draft, organization_id, actor_user_id):
        return list(files), list(deletions or [])
    return build


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
        inst = GitHubInstallation(
            organization_id=api_context.organization.id,
            installation_id=556677,
            account_login="acme-labs",
            account_type="Organization",
            permissions={},
        )
        api_context.db.add(inst)
        api_context.db.flush()
        api_context.repository.github_installation_id = inst.id
        api_context.db.commit()
    return created["id"]


def _draft(api_context, request_id: str, *, branch="codedna/ai/feature-abc", base="main") -> DraftPullRequest:
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
    api_context.db.add(draft)
    api_context.db.commit()
    return draft


def _validation(api_context, request_id: str, *, status="passed") -> ValidationRun:
    run = ValidationRun(
        organization_id=api_context.organization.id,
        engineering_request_id=uuid.UUID(request_id),
        status=status,
        checks=[{"name": "pytest", "status": "passed"}],
        report={"success": status == "passed", "passed": ["pytest"]},
    )
    api_context.db.add(run)
    api_context.db.commit()
    return run


def _creator(api_context, **kwargs) -> GitHubDraftPRCreator:
    return GitHubDraftPRCreator(api_context.db, **kwargs)


def test_creates_draft_pr_with_mocked_github(api_context, monkeypatch) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    _draft(api_context, request_id)
    _validation(api_context, request_id, status="passed")

    client = FakeClient()
    draft = _creator(
        api_context, client=client, change_builder=_builder([("src/feature.py", "x = 1\n")])
    ).create(
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


def test_refuses_when_validation_not_passed(api_context, monkeypatch) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    _draft(api_context, request_id)
    _validation(api_context, request_id, status="failed")
    with pytest.raises(AppError) as exc:
        _creator(api_context, client=FakeClient(), change_builder=_builder([("a.py", "1")])).create(
            engineering_request_id=uuid.UUID(request_id),
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
        )
    assert "validation has not passed" in str(exc.value).lower()


def test_refuses_when_no_validation_run(api_context, monkeypatch) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    _draft(api_context, request_id)  # no ValidationRun
    with pytest.raises(AppError):
        _creator(api_context, client=FakeClient(), change_builder=_builder([("a.py", "1")])).create(
            engineering_request_id=uuid.UUID(request_id),
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
        )


def test_refuses_default_branch(api_context, monkeypatch) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    _draft(api_context, request_id, branch="main", base="main")
    _validation(api_context, request_id, status="passed")
    with pytest.raises(AppError):
        _creator(api_context, client=FakeClient(), change_builder=_builder([("a.py", "1")])).create(
            engineering_request_id=uuid.UUID(request_id),
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
        )


def test_refuses_forbidden_files(api_context, monkeypatch) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    _draft(api_context, request_id)
    _validation(api_context, request_id, status="passed")
    with pytest.raises(AppError):
        _creator(api_context, client=FakeClient(), change_builder=_builder([(".env", "SECRET=1")])).create(
            engineering_request_id=uuid.UUID(request_id),
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
        )


def test_refuses_missing_installation(api_context, monkeypatch) -> None:
    request_id = _approved_request(api_context, monkeypatch, connect=False)
    _draft(api_context, request_id)
    _validation(api_context, request_id, status="passed")
    with pytest.raises(AppError):
        _creator(api_context, client=FakeClient(), change_builder=_builder([("a.py", "1")])).create(
            engineering_request_id=uuid.UUID(request_id),
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
        )


def test_idempotent_duplicate_prevention(api_context, monkeypatch) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    _draft(api_context, request_id)
    _validation(api_context, request_id, status="passed")

    first = _creator(api_context, client=FakeClient(), change_builder=_builder([("a.py", "1")])).create(
        engineering_request_id=uuid.UUID(request_id),
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    second_client = FakeClient()
    second = _creator(api_context, client=second_client, change_builder=_builder([("a.py", "1")])).create(
        engineering_request_id=uuid.UUID(request_id),
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    assert first.github_pr_url == second.github_pr_url
    assert second_client.pushed is None  # no second push


class _FakeGitHub422:
    """Minimal GitHub integration that simulates 422 'already exists' responses."""

    def __init__(self, *, branch_exists: bool, pr_exists: bool) -> None:
        self._branch_exists = branch_exists
        self._pr_exists = pr_exists
        self.created_branch = False
        self.created_pr = False
        self.puts: list[str] = []

    def get_installation_token(self, installation_id):
        return "tok"

    def get_branch_sha(self, *, token, owner, repo, branch):
        from app.core.errors import IntegrationError

        # Base branch always resolves; the head branch existence is configurable.
        if branch == "main":
            return "base-sha"
        if self._branch_exists:
            return "existing-head-sha"
        raise IntegrationError("not found", upstream_status=404)

    def create_branch(self, *, token, owner, repo, branch, sha):
        from app.core.errors import IntegrationError

        if self._branch_exists:
            raise IntegrationError("Reference already exists", upstream_status=422)
        self.created_branch = True
        return {"ref": branch}

    def get_content_sha(self, *, token, owner, repo, path, ref):
        return None

    def put_file(self, *, token, owner, repo, path, content_b64, message, branch, sha=None):
        self.puts.append(path)
        return {}

    def delete_file(self, **kwargs):
        return {}

    def create_pull_request(self, *, token, owner, repo, head, base, title, body, draft=True):
        from app.core.errors import IntegrationError

        if self._pr_exists:
            raise IntegrationError("A pull request already exists", upstream_status=422)
        self.created_pr = True
        return {"number": 7, "html_url": "https://github.com/acme-labs/payments-api/pull/7"}

    def list_pull_requests(self, *, token, owner, repo, head=None, state="all"):
        if self._pr_exists:
            return [{"number": 99, "html_url": "https://github.com/acme-labs/payments-api/pull/99"}]
        return []


def _real_client(gh):
    from app.services.agent.github_draft_pr_creator import DefaultDraftPRClient

    return DefaultDraftPRClient(integration=gh)


def test_duplicate_branch_422_is_reused(api_context, monkeypatch) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    _draft(api_context, request_id)
    _validation(api_context, request_id, status="passed")

    gh = _FakeGitHub422(branch_exists=True, pr_exists=False)
    draft = _creator(
        api_context, client=_real_client(gh), change_builder=_builder([("src/feature.py", "x = 1\n")])
    ).create(
        engineering_request_id=uuid.UUID(request_id),
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    # Branch already existed: not recreated, but files still pushed and PR opened.
    assert gh.created_branch is False
    assert "src/feature.py" in gh.puts
    assert draft.is_pushed is True
    assert draft.github_pr_number == 7
    assert draft.already_exists is False  # the PR itself was newly created


def test_duplicate_pr_422_returns_existing(api_context, monkeypatch) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    _draft(api_context, request_id)
    _validation(api_context, request_id, status="passed")

    gh = _FakeGitHub422(branch_exists=True, pr_exists=True)
    draft = _creator(
        api_context, client=_real_client(gh), change_builder=_builder([("src/feature.py", "x = 1\n")])
    ).create(
        engineering_request_id=uuid.UUID(request_id),
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    # The existing PR is returned instead of creating a duplicate.
    assert gh.created_pr is False
    assert draft.is_pushed is True
    assert draft.github_pr_number == 99
    assert "pull/99" in draft.github_pr_url
    assert draft.already_exists is True

    actions = {r.action for r in api_context.db.query(AuditLog).filter(AuditLog.target_id == request_id).all()}
    assert "draft_pr_already_exists" in actions


def test_duplicate_pr_surfaced_in_response_schema(api_context, monkeypatch) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    _draft(api_context, request_id)
    _validation(api_context, request_id, status="passed")

    gh = _FakeGitHub422(branch_exists=True, pr_exists=True)
    draft = _creator(
        api_context, client=_real_client(gh), change_builder=_builder([("src/feature.py", "x=1\n")])
    ).create(
        engineering_request_id=uuid.UUID(request_id),
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    # Serialize through the response schema to confirm the UI receives the flag.
    from app.schemas.draft_pull_request import DraftPullRequestRead

    payload = DraftPullRequestRead.model_validate(draft, from_attributes=True)
    assert payload.already_exists is True
    assert payload.github_pr_number == 99


def test_response_schema_defaults_already_exists_false(api_context, monkeypatch) -> None:
    # A freshly prepared draft (never serialized through create) defaults to False.
    request_id = _approved_request(api_context, monkeypatch)
    draft = _draft(api_context, request_id)
    from app.schemas.draft_pull_request import DraftPullRequestRead

    payload = DraftPullRequestRead.model_validate(draft, from_attributes=True)
    assert payload.already_exists is False


def test_org_isolation(api_context) -> None:
    other_id = str(uuid.uuid4())
    with pytest.raises(NotFoundError):
        _creator(api_context, client=FakeClient(), change_builder=_builder([("a.py", "1")])).create(
            engineering_request_id=uuid.UUID(other_id),
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
        )
