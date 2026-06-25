from __future__ import annotations

import json

from app.models.audit import AuditLog
from app.services.agent.code_generation_service import CodeGenerationService
from app.services.engineering_planning_service import EngineeringPlanningService

BASE = "/api/v1/engineering-requests"


def _approved_request(api_context, monkeypatch) -> str:
    plan_payload = {
        "summary": "Plan",
        "affected_files": [{"path": "backend/app/services/scan_service.py", "reason": "logic"}],
        "implementation_plan": ["Step one", "Step two"],
        "test_plan": ["unit tests"],
        "risk_level": "low",
        "safety_notes": [],
    }
    monkeypatch.setattr(
        EngineeringPlanningService, "_call_ai", lambda self, prompt: json.dumps(plan_payload)
    )
    created = api_context.client.post(
        BASE,
        json={
            "title": "Speed up scans",
            "description": "Make scans faster.",
            "request_type": "performance",
            "repository_id": str(api_context.repository.id),
        },
    ).json()
    api_context.client.post(f"{BASE}/{created['id']}/analyze")
    api_context.client.post(f"{BASE}/{created['id']}/approve-plan")
    return created["id"]


def _mock_codegen(monkeypatch, payload: dict) -> None:
    monkeypatch.setattr(CodeGenerationService, "_call_ai", lambda self, prompt: json.dumps(payload))


def test_code_generation_preview_with_mocked_ai(api_context, monkeypatch) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    _mock_codegen(
        monkeypatch,
        {
            "summary": "Add caching layer.",
            "affected_files": [
                {"path": "backend/app/services/scan_service.py", "change_type": "modify", "reason": "cache"}
            ],
            "diff_preview": "--- a/x\n+++ b/x\n+ cache = {}\n",
            "implementation_tasks": ["Add cache", "Wire it in"],
            "documentation_updates": ["Update README"],
            "tests_to_create": ["test_cache"],
        },
    )

    response = api_context.client.post(f"{BASE}/{request_id}/code-generation")
    assert response.status_code == 200, response.text
    preview = response.json()

    assert preview["summary"] == "Add caching layer."
    assert preview["affected_files"][0]["change_type"] == "modify"
    assert "cache" in preview["diff_preview"]
    assert preview["implementation_tasks"] == ["Add cache", "Wire it in"]
    assert preview["tests_to_create"] == ["test_cache"]
    assert preview["estimated_changes"]["files"] == 1
    assert preview["ai_available"] is True

    actions = {
        row.action
        for row in api_context.db.query(AuditLog).filter(AuditLog.target_id == request_id).all()
    }
    assert "code_generation_previewed" in actions

    fetched = api_context.client.get(f"{BASE}/{request_id}/code-generation")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == preview["id"]


def test_code_generation_degrades_without_ai(api_context, monkeypatch) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    monkeypatch.setattr(CodeGenerationService, "_call_ai", lambda self, prompt: None)

    preview = api_context.client.post(f"{BASE}/{request_id}/code-generation").json()
    assert preview["ai_available"] is False
    # Falls back to plan-derived files and an illustrative diff.
    assert len(preview["affected_files"]) >= 1
    assert preview["diff_preview"]
    assert "illustrative" in preview["diff_preview"].lower()


def test_code_generation_requires_approved(api_context, monkeypatch) -> None:
    monkeypatch.setattr(EngineeringPlanningService, "_call_ai", lambda self, prompt: None)
    created = api_context.client.post(
        BASE, json={"title": "Not approved", "description": "x", "request_type": "bug"}
    ).json()
    api_context.client.post(f"{BASE}/{created['id']}/analyze")  # plan_ready, not approved
    assert api_context.client.post(f"{BASE}/{created['id']}/code-generation").status_code == 400


def test_code_generation_org_isolation(api_context, monkeypatch) -> None:
    import uuid

    other_id = str(uuid.uuid4())
    assert api_context.client.post(f"{BASE}/{other_id}/code-generation").status_code == 404
    assert api_context.client.get(f"{BASE}/{other_id}/code-generation").status_code == 404
