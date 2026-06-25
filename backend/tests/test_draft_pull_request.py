from __future__ import annotations

import json
import uuid

from app.models.audit import AuditLog
from app.services.engineering_planning_service import EngineeringPlanningService

BASE = "/api/v1/engineering-requests"


def _approved_request(api_context, monkeypatch) -> str:
    plan_payload = {
        "summary": "Add retry backoff.",
        "affected_files": [{"path": "backend/app/workers/tasks.py", "reason": "retry"}],
        "implementation_plan": ["Add backoff", "Add test"],
        "test_plan": ["unit"],
        "risk_level": "medium",
        "safety_notes": [],
    }
    monkeypatch.setattr(
        EngineeringPlanningService, "_call_ai", lambda self, prompt: json.dumps(plan_payload)
    )
    created = api_context.client.post(
        BASE,
        json={
            "title": "Harden retry path",
            "description": "Make retries reliable.",
            "request_type": "bug",
            "repository_id": str(api_context.repository.id),
        },
    ).json()
    api_context.client.post(f"{BASE}/{created['id']}/analyze")
    api_context.client.post(f"{BASE}/{created['id']}/approve-plan")
    return created["id"]


def test_prepare_draft_pull_request(api_context, monkeypatch) -> None:
    request_id = _approved_request(api_context, monkeypatch)

    response = api_context.client.post(f"{BASE}/{request_id}/draft-pr")
    assert response.status_code == 200, response.text
    draft = response.json()

    assert draft["branch_name"].startswith("codedna/ai/")
    assert draft["base_branch"] == "main"
    assert draft["branch_name"] != draft["base_branch"]
    assert draft["title"].startswith("[CodeDNA AI]")
    assert draft["is_pushed"] is False
    assert draft["human_approval_required"] is True
    assert draft["status"] == "draft"
    assert len(draft["commit_plan"]) >= 1
    assert draft["commit_plan"][0]["message"].startswith("fix:")  # bug -> fix
    assert "codedna-ai" in draft["labels"]
    assert "needs-human-review" in draft["labels"]
    # Body explicitly states nothing was pushed/opened.
    assert "not" in draft["body"].lower() and "pull request" in draft["body"].lower()

    actions = {
        row.action
        for row in api_context.db.query(AuditLog).filter(AuditLog.target_id == request_id).all()
    }
    assert "draft_pull_request_prepared" in actions

    fetched = api_context.client.get(f"{BASE}/{request_id}/draft-pr")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == draft["id"]


def test_draft_pr_requires_approved(api_context, monkeypatch) -> None:
    monkeypatch.setattr(EngineeringPlanningService, "_call_ai", lambda self, prompt: None)
    created = api_context.client.post(
        BASE, json={"title": "Not approved", "description": "x", "request_type": "bug"}
    ).json()
    api_context.client.post(f"{BASE}/{created['id']}/analyze")  # plan_ready
    assert api_context.client.post(f"{BASE}/{created['id']}/draft-pr").status_code == 400


def test_draft_pr_org_isolation(api_context) -> None:
    other_id = str(uuid.uuid4())
    assert api_context.client.post(f"{BASE}/{other_id}/draft-pr").status_code == 404
    assert api_context.client.get(f"{BASE}/{other_id}/draft-pr").status_code == 404


def test_draft_pr_never_pushed(api_context, monkeypatch) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    draft = api_context.client.post(f"{BASE}/{request_id}/draft-pr").json()
    # Regenerate should remain not-pushed and human-gated.
    again = api_context.client.post(f"{BASE}/{request_id}/draft-pr").json()
    assert draft["id"] == again["id"]
    assert again["is_pushed"] is False
