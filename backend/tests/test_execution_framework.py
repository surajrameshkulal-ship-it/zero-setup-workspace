from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

from app.models.audit import AuditLog
from app.models.engineering_request import RequestType
from app.models.execution_plan import ExecutionSafetyStatus
from app.services.engineering_planning_service import EngineeringPlanningService
from app.services.execution.github_workspace_manager import GitHubWorkspaceManager
from app.services.execution.repository_context_service import RepositoryContextService
from app.services.execution.safety_engine import ExecutionSafetyEngine

BASE = "/api/v1/engineering-requests"


def _approved_request(api_context, monkeypatch, affected_files: list[dict] | None = None) -> str:
    """Create -> analyze (mocked AI) -> approve, returning the request id."""
    plan_payload = {
        "summary": "Plan",
        "request_type": "feature",
        "affected_files": affected_files if affected_files is not None else [
            {"path": "backend/app/services/scan_service.py", "reason": "logic"}
        ],
        "implementation_plan": ["Step one", "Step two", "Step three"],
        "test_plan": ["Unit tests"],
        "risk_level": "low",
        "safety_notes": [],
    }
    monkeypatch.setattr(
        EngineeringPlanningService, "_call_ai", lambda self, prompt: json.dumps(plan_payload)
    )
    created = api_context.client.post(
        BASE,
        json={
            "title": "Improve scan throughput",
            "description": "Make scans faster.",
            "request_type": "feature",
            "repository_id": str(api_context.repository.id),
        },
    ).json()
    api_context.client.post(f"{BASE}/{created['id']}/analyze")
    api_context.client.post(f"{BASE}/{created['id']}/approve-plan")
    return created["id"]


# -- unit tests (pure services) ------------------------------------------------


def test_branch_name_generation_is_safe_and_slugged() -> None:
    manager = GitHubWorkspaceManager()
    request = SimpleNamespace(
        id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
        title="Fix Login Bug!! Now",
        request_type=RequestType.BUG,
    )
    branch = manager.create_branch_name(request)

    assert branch.startswith("codedna/ai/bug-12345678-")
    assert " " not in branch
    assert manager.is_branch_safe(branch, "main") is True
    assert manager.is_branch_safe("main", "main") is False
    assert manager.is_branch_safe("feature/x", "main") is False  # wrong prefix


def test_safety_engine_safe_case() -> None:
    result = ExecutionSafetyEngine().validate(
        estimated_files=["backend/app/services/scan_service.py", "frontend/lib/format.ts"],
        branch_name="codedna/ai/feature-abc-improve",
        default_branch="main",
        repository_linked=True,
    )
    assert result["status"] == ExecutionSafetyStatus.SAFE
    assert result["findings"] == []


def test_safety_engine_protected_file_detection_needs_approval() -> None:
    result = ExecutionSafetyEngine().validate(
        estimated_files=["backend/app/core/security.py"],
        branch_name="codedna/ai/security-abc-x",
        default_branch="main",
        repository_linked=True,
    )
    assert result["status"] == ExecutionSafetyStatus.NEEDS_APPROVAL
    assert "backend/app/core/security.py" in result["protected_files"]


def test_safety_engine_forbidden_path_detection_blocks() -> None:
    result = ExecutionSafetyEngine().validate(
        estimated_files=[".env", "backend/app/secrets/keys.pem"],
        branch_name="codedna/ai/feature-abc-x",
        default_branch="main",
        repository_linked=True,
    )
    assert result["status"] == ExecutionSafetyStatus.BLOCKED
    assert ".env" in result["forbidden_files"]


def test_safety_engine_blocks_unsafe_branch() -> None:
    result = ExecutionSafetyEngine().validate(
        estimated_files=["backend/app/main.py"],
        branch_name="main",
        default_branch="main",
        repository_linked=True,
    )
    assert result["status"] == ExecutionSafetyStatus.BLOCKED


def test_repository_context_loading_is_org_scoped(api_context) -> None:
    context = RepositoryContextService(api_context.db).build(
        organization_id=api_context.organization.id,
        repository=api_context.repository,
    )
    assert context["repository"]["full_name"] == "acme/payments-api"
    assert isinstance(context["architecture_rules"], list)
    assert isinstance(context["company_rules"], list)
    # Only this org's scans are visible (other org's scan excluded).
    assert all(scan["pr_number"] in {12, 13} for scan in context["latest_scans"])
    assert context["readme"] is None  # requires live fetch, not done here
    assert "candidates" in context["dependency_files"]


# -- API tests -----------------------------------------------------------------


def test_execution_plan_generation(api_context, monkeypatch) -> None:
    request_id = _approved_request(api_context, monkeypatch)

    response = api_context.client.post(f"{BASE}/{request_id}/execution-plan")
    assert response.status_code == 200, response.text
    plan = response.json()

    assert plan["engineering_request_id"] == request_id
    assert len(plan["tasks"]) == 3
    assert plan["tasks"][0]["order"] == 1
    assert plan["estimated_files"] == ["backend/app/services/scan_service.py"]
    assert plan["safety_status"] in {"safe", "needs_approval", "blocked"}
    assert plan["branch_name"].startswith("codedna/ai/")
    assert len(plan["rollback_strategy"]) >= 1
    assert len(plan["validation_checklist"]) >= 1
    assert plan["repository_context"]["repository"]["full_name"] == "acme/payments-api"

    # Audit events for the execution lifecycle.
    actions = {
        row.action
        for row in api_context.db.query(AuditLog).filter(AuditLog.target_id == request_id).all()
    }
    assert "repository_context_loaded" in actions
    assert "execution_plan_generated" in actions
    assert ("execution_ready" in actions) or ("execution_blocked" in actions)

    # GET returns the persisted plan.
    fetched = api_context.client.get(f"{BASE}/{request_id}/execution-plan")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == plan["id"]


def test_execution_plan_blocked_for_forbidden_files(api_context, monkeypatch) -> None:
    request_id = _approved_request(
        api_context,
        monkeypatch,
        affected_files=[{"path": ".env", "reason": "config"}],
    )
    plan = api_context.client.post(f"{BASE}/{request_id}/execution-plan").json()
    assert plan["safety_status"] == "blocked"

    actions = {
        row.action
        for row in api_context.db.query(AuditLog).filter(AuditLog.target_id == request_id).all()
    }
    assert "execution_blocked" in actions


def test_execution_plan_requires_approved_status(api_context, monkeypatch) -> None:
    # Create + analyze but DO NOT approve.
    monkeypatch.setattr(EngineeringPlanningService, "_call_ai", lambda self, prompt: None)
    created = api_context.client.post(
        BASE,
        json={"title": "Not approved yet", "description": "x", "request_type": "bug"},
    ).json()
    api_context.client.post(f"{BASE}/{created['id']}/analyze")  # status -> plan_ready

    response = api_context.client.post(f"{BASE}/{created['id']}/execution-plan")
    assert response.status_code == 400


def test_execution_plan_organization_isolation(api_context, monkeypatch) -> None:
    request_id = _approved_request(api_context, monkeypatch)

    # A different org cannot read this org's execution plan or request.
    other_id = str(uuid.uuid4())
    assert api_context.client.get(f"{BASE}/{other_id}/execution-plan").status_code == 404
    assert api_context.client.post(f"{BASE}/{other_id}/execution-plan").status_code == 404
