from __future__ import annotations

import json
import uuid

from app.models.audit import AuditLog
from app.models.draft_pull_request import DraftPullRequest
from app.services.agent.validation_service import ValidationService
from app.services.engineering_planning_service import EngineeringPlanningService

BASE = "/api/v1/engineering-requests"


def _approved_request(api_context, monkeypatch) -> str:
    plan_payload = {
        "summary": "ok",
        "affected_files": [{"path": "backend/app/services/scan_service.py", "reason": "x"}],
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
            "title": "Add cache",
            "description": "Cache results.",
            "request_type": "performance",
            "repository_id": str(api_context.repository.id),
        },
    ).json()
    api_context.client.post(f"{BASE}/{created['id']}/analyze")
    api_context.client.post(f"{BASE}/{created['id']}/approve-plan")
    return created["id"]


# Custom validators/fixers via the service (unit-level), plus API-level default run.


def test_validation_success_produces_draft_pr_via_service(api_context, monkeypatch) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    service = ValidationService(api_context.db)

    all_pass = lambda ctx, attempt: [{"name": "pytest", "status": "passed", "details": "ok"}]  # noqa: E731

    run = service.run(
        engineering_request_id=uuid.UUID(request_id),
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        validator=all_pass,
    )
    assert run.status == "passed"
    assert run.draft_pull_request_id is not None
    # Draft PR was actually created (metadata only, never pushed).
    draft = api_context.db.get(DraftPullRequest, run.draft_pull_request_id)
    assert draft is not None and draft.is_pushed is False


def test_validation_failure_returns_report_no_draft(api_context, monkeypatch) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    service = ValidationService(api_context.db)

    always_fail = lambda ctx, attempt: [  # noqa: E731
        {"name": "pytest", "status": "failed", "details": "2 tests failed"}
    ]
    no_fix = lambda failed, ctx, attempt: []  # noqa: E731

    run = service.run(
        engineering_request_id=uuid.UUID(request_id),
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        validator=always_fail,
        auto_fixer=no_fix,
        max_attempts=3,
    )
    assert run.status == "failed"
    assert run.draft_pull_request_id is None
    assert run.report["success"] is False
    assert "pytest" in run.report["failed"]
    # No fix possible -> stops after the first attempt.
    assert run.attempts == 1


def test_validation_autofix_retry_then_success(api_context, monkeypatch) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    service = ValidationService(api_context.db)

    # Fails on attempt 1, passes from attempt 2 onward (simulating an applied fix).
    def validator(ctx, attempt):
        status = "failed" if attempt < 2 else "passed"
        return [{"name": "npm_build", "status": status, "details": f"attempt {attempt}"}]

    def auto_fixer(failed, ctx, attempt):
        return [{"check": failed[0]["name"], "fix": "adjusted import", "attempt": attempt}]

    run = service.run(
        engineering_request_id=uuid.UUID(request_id),
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        validator=validator,
        auto_fixer=auto_fixer,
        max_attempts=3,
    )
    assert run.status == "passed"
    assert run.attempts == 2
    assert len(run.auto_fixes_applied) == 1
    assert run.draft_pull_request_id is not None


def test_validation_default_pipeline_via_api(api_context, monkeypatch) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    response = api_context.client.post(f"{BASE}/{request_id}/validate")
    assert response.status_code == 200, response.text
    run = response.json()
    # Default planned checks + rule checks all pass (no blocked execution plan).
    names = {c["name"] for c in run["checks"]}
    assert {"pytest", "npm_build", "semgrep", "codedna_review", "company_rules", "architecture_rules"} <= names
    assert run["status"] == "passed"
    assert run["draft_pull_request_id"] is not None

    actions = {
        row.action
        for row in api_context.db.query(AuditLog).filter(AuditLog.target_id == request_id).all()
    }
    assert "validation_started" in actions
    assert "validation_passed" in actions

    fetched = api_context.client.get(f"{BASE}/{request_id}/validation")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == run["id"]


def test_validation_requires_approved(api_context, monkeypatch) -> None:
    monkeypatch.setattr(EngineeringPlanningService, "_call_ai", lambda self, prompt: None)
    created = api_context.client.post(
        BASE, json={"title": "Pending request", "description": "y", "request_type": "bug"}
    ).json()
    api_context.client.post(f"{BASE}/{created['id']}/analyze")  # plan_ready
    assert api_context.client.post(f"{BASE}/{created['id']}/validate").status_code == 400


def test_validation_org_isolation(api_context) -> None:
    other_id = str(uuid.uuid4())
    assert api_context.client.post(f"{BASE}/{other_id}/validate").status_code == 404
    assert api_context.client.get(f"{BASE}/{other_id}/validation").status_code == 404
