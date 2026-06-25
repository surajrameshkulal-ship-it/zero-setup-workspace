from __future__ import annotations

import json

from app.models.audit import AuditLog
from app.models.engineering_request import (
    EngineeringRequest,
    RequestPriority,
    RequestStatus,
    RequestType,
)
from app.services.engineering_planning_service import EngineeringPlanningService

BASE = "/api/v1/engineering-requests"


def _create(api_context, **overrides) -> dict:
    payload = {
        "title": "Fix flaky scan retry",
        "description": "The retry path occasionally drops a scan. Make it reliable.",
        "request_type": "bug",
        "priority": "high",
        "repository_id": str(api_context.repository.id),
    }
    payload.update(overrides)
    response = api_context.client.post(BASE, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _mock_ai(monkeypatch, payload: dict) -> None:
    monkeypatch.setattr(
        EngineeringPlanningService,
        "_call_ai",
        lambda self, prompt: json.dumps(payload),
    )


def test_create_request(api_context) -> None:
    body = _create(api_context)

    assert body["title"] == "Fix flaky scan retry"
    assert body["request_type"] == "bug"
    assert body["priority"] == "high"
    assert body["status"] == "submitted"
    assert body["repository_id"] == str(api_context.repository.id)
    assert body["repository_full_name"] == "acme/payments-api"
    assert body["created_by_user_id"] == str(api_context.user.id)

    # Audit log written.
    actions = [
        row.action
        for row in api_context.db.query(AuditLog)
        .filter(AuditLog.target_id == body["id"])
        .all()
    ]
    assert "engineering_request_created" in actions


def test_create_request_without_repository(api_context) -> None:
    body = _create(api_context, repository_id=None)
    assert body["repository_id"] is None
    assert body["repository_full_name"] is None


def test_create_request_rejects_foreign_repository(api_context) -> None:
    response = api_context.client.post(
        BASE,
        json={
            "title": "Cross-tenant attempt",
            "description": "Should not be allowed.",
            "request_type": "feature",
            "repository_id": str(api_context.other_repository.id),
        },
    )
    assert response.status_code == 404


def test_list_requests(api_context) -> None:
    first = _create(api_context, title="First request")
    second = _create(api_context, title="Second request")

    response = api_context.client.get(BASE)
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert {first["id"], second["id"]} <= ids
    assert all("description" not in item for item in response.json())  # list item is slim


def test_get_request(api_context) -> None:
    created = _create(api_context)
    response = api_context.client.get(f"{BASE}/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["description"].startswith("The retry path")


def test_analyze_request_with_mocked_ai(api_context, monkeypatch) -> None:
    _mock_ai(
        monkeypatch,
        {
            "summary": "Harden the Celery retry path.",
            "request_type": "bug",
            "affected_files": [
                {"path": "backend/app/workers/tasks.py", "reason": "retry logic"}
            ],
            "implementation_plan": ["Reproduce", "Fix backoff", "Add test"],
            "test_plan": ["Unit test for retry exhaustion"],
            "risk_level": "medium",
            "allowed_changes": ["worker source code", "tests"],
            "safety_notes": ["Keep changes scoped to the worker."],
        },
    )

    created = _create(api_context)
    response = api_context.client.post(f"{BASE}/{created['id']}/analyze")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["status"] == "plan_ready"
    assert body["ai_summary"] == "Harden the Celery retry path."
    assert body["affected_files"][0]["path"] == "backend/app/workers/tasks.py"
    assert body["implementation_plan"] == ["Reproduce", "Fix backoff", "Add test"]
    assert body["test_plan"] == ["Unit test for retry exhaustion"]
    assert body["risk_level"] == "medium"

    # Safety constraints are ALWAYS attached, regardless of AI output.
    safety = body["safety_notes"]
    assert safety["human_approval_required"] is True
    forbidden_blob = " ".join(safety["forbidden"]).lower()
    assert "deploy" in forbidden_blob
    assert "main" in forbidden_blob
    assert "secret" in forbidden_blob
    assert "merg" in forbidden_blob  # merging requires human approval

    # Audit trail for the analysis lifecycle.
    actions = [
        row.action
        for row in api_context.db.query(AuditLog)
        .filter(AuditLog.target_id == created["id"])
        .all()
    ]
    assert "engineering_request_analysis_started" in actions
    assert "engineering_request_plan_ready" in actions


def test_analyze_security_request_forces_high_risk(api_context, monkeypatch) -> None:
    # AI says low risk, but a security request must be escalated.
    _mock_ai(
        monkeypatch,
        {
            "summary": "Tweak the login flow.",
            "request_type": "security",
            "affected_files": [{"path": "backend/app/core/security.py", "reason": "auth"}],
            "implementation_plan": ["Adjust token handling"],
            "test_plan": ["Auth tests"],
            "risk_level": "low",
            "safety_notes": [],
        },
    )

    created = _create(
        api_context,
        title="Update authentication token expiry",
        request_type="security",
    )
    body = api_context.client.post(f"{BASE}/{created['id']}/analyze").json()

    assert body["risk_level"] == "high"
    notes_blob = " ".join(body["safety_notes"]["notes"]).lower()
    assert "high-risk" in notes_blob


def test_analyze_degrades_gracefully_without_ai(api_context, monkeypatch) -> None:
    # AI unavailable -> deterministic fallback plan, still safe and plan_ready.
    monkeypatch.setattr(EngineeringPlanningService, "_call_ai", lambda self, prompt: None)

    created = _create(api_context)
    body = api_context.client.post(f"{BASE}/{created['id']}/analyze").json()

    assert body["status"] == "plan_ready"
    assert body["ai_summary"]
    assert len(body["implementation_plan"]) >= 1
    assert body["safety_notes"]["human_approval_required"] is True


def test_approve_plan(api_context, monkeypatch) -> None:
    _mock_ai(monkeypatch, {"summary": "ok", "risk_level": "low"})
    created = _create(api_context)
    api_context.client.post(f"{BASE}/{created['id']}/analyze")

    response = api_context.client.post(f"{BASE}/{created['id']}/approve-plan")
    assert response.status_code == 200
    assert response.json()["status"] == "approved"

    actions = [
        row.action
        for row in api_context.db.query(AuditLog)
        .filter(AuditLog.target_id == created["id"])
        .all()
    ]
    assert "engineering_request_approved" in actions


def test_approve_requires_plan_ready(api_context) -> None:
    created = _create(api_context)  # still 'submitted'
    response = api_context.client.post(f"{BASE}/{created['id']}/approve-plan")
    assert response.status_code == 400


def test_reject_plan(api_context, monkeypatch) -> None:
    _mock_ai(monkeypatch, {"summary": "ok", "risk_level": "low"})
    created = _create(api_context)
    api_context.client.post(f"{BASE}/{created['id']}/analyze")

    response = api_context.client.post(
        f"{BASE}/{created['id']}/reject-plan",
        json={"reason": "Scope too large for now."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["safety_notes"]["rejection_reason"] == "Scope too large for now."

    actions = [
        row.action
        for row in api_context.db.query(AuditLog)
        .filter(AuditLog.target_id == created["id"])
        .all()
    ]
    assert "engineering_request_rejected" in actions


def test_requests_are_scoped_to_current_organization(api_context) -> None:
    # A request belonging to another org must be invisible and inaccessible.
    foreign = EngineeringRequest(
        organization_id=api_context.other_organization.id,
        title="Foreign request",
        description="Belongs to another tenant.",
        request_type=RequestType.FEATURE,
        priority=RequestPriority.MEDIUM,
        status=RequestStatus.SUBMITTED,
        affected_files=[],
        implementation_plan=[],
        test_plan=[],
        safety_notes={},
    )
    api_context.db.add(foreign)
    api_context.db.commit()

    listed = api_context.client.get(BASE).json()
    assert str(foreign.id) not in {item["id"] for item in listed}

    assert api_context.client.get(f"{BASE}/{foreign.id}").status_code == 404
    assert api_context.client.post(f"{BASE}/{foreign.id}/analyze").status_code == 404
    assert api_context.client.post(f"{BASE}/{foreign.id}/approve-plan").status_code == 404
