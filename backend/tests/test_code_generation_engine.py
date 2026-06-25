from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.core.errors import AppError, IntegrationError, NotFoundError
from app.models.engineering_request import (
    EngineeringRequest,
    RequestPriority,
    RequestStatus,
    RequestType,
)
from app.models.rule import ArchitectureRule, CompanyRule, CompanyRuleType, Severity
from app.services.agent.code_generation_engine import CodeGenerationEngine
from app.services.engineering_planning_service import EngineeringPlanningService

BASE = "/api/v1/engineering-requests"


def _materialization(tmp_path) -> SimpleNamespace:
    return SimpleNamespace(
        materialized=True,
        workspace_path=str(tmp_path),
        default_branch="main",
        target_branch="codedna/ai/feature-abc",
        language_hints=["Python"],
    )


def _approved_request(api_context, monkeypatch) -> str:
    plan_payload = {
        "summary": "ok",
        "affected_files": [{"path": "backend/app/services/scan_service.py", "reason": "logic"}],
        "implementation_plan": ["do it"],
        "test_plan": ["test it"],
        "risk_level": "low",
        "safety_notes": [],
    }
    monkeypatch.setattr(
        EngineeringPlanningService, "_call_ai", lambda self, prompt: json.dumps(plan_payload)
    )
    created = api_context.client.post(
        BASE,
        json={
            "title": "Add caching",
            "description": "Cache scan results.",
            "request_type": "performance",
            "repository_id": str(api_context.repository.id),
        },
    ).json()
    api_context.client.post(f"{BASE}/{created['id']}/analyze")
    api_context.client.post(f"{BASE}/{created['id']}/approve-plan")
    return created["id"]


def _mock_codegen(monkeypatch, payload: dict) -> None:
    monkeypatch.setattr(CodeGenerationEngine, "_call_ai", lambda self, prompt: json.dumps(payload))


def test_successful_generation(api_context, monkeypatch, tmp_path) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    _mock_codegen(
        monkeypatch,
        {
            "changes": [
                {
                    "path": "backend/app/services/scan_service.py",
                    "operation": "modify",
                    "language": "Python",
                    "operations": [
                        {"type": "insert", "target": "top", "content": "CACHE = {}\n", "explanation": "cache"}
                    ],
                    "explanation": "add caching",
                },
                {
                    "path": "backend/app/services/cache.py",
                    "operation": "create",
                    "language": "Python",
                    "operations": [{"type": "create", "content": "x = 1\n", "explanation": "new module"}],
                    "explanation": "new cache module",
                },
            ],
            "tests_to_add": ["test_cache"],
            "documentation_updates": ["Update README"],
            "estimated_lines_changed": 12,
            "confidence_score": 0.8,
        },
    )

    engine = CodeGenerationEngine(api_context.db)
    plan = engine.generate(
        engineering_request_id=uuid.UUID(request_id),
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        materialization=_materialization(tmp_path),
    )

    assert plan.files_to_modify == ["backend/app/services/scan_service.py"]
    assert plan.files_to_create == ["backend/app/services/cache.py"]
    assert plan.files_to_delete == []
    assert plan.changes[0]["operation"] == "modify"
    assert plan.changes[0]["language"] == "Python"
    assert plan.tests_to_add == ["test_cache"]
    assert plan.estimated_lines_changed == 12
    assert plan.confidence_score == 0.8
    assert plan.ai_available is True


def test_blocked_generation_not_approved(api_context, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(EngineeringPlanningService, "_call_ai", lambda self, prompt: None)
    created = api_context.client.post(
        BASE, json={"title": "Not approved", "description": "x", "request_type": "bug"}
    ).json()
    api_context.client.post(f"{BASE}/{created['id']}/analyze")  # plan_ready, not approved

    engine = CodeGenerationEngine(api_context.db)
    with pytest.raises(AppError):
        engine.generate(
            engineering_request_id=uuid.UUID(created["id"]),
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
            materialization=_materialization(tmp_path),
        )


def test_blocked_generation_requires_materialization(api_context, monkeypatch) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    engine = CodeGenerationEngine(api_context.db)
    with pytest.raises(AppError):
        engine.generate(
            engineering_request_id=uuid.UUID(request_id),
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
            materialization=None,
        )


def test_provider_unavailable_raises(api_context, monkeypatch, tmp_path) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    # AI enabled, but no provider key configured -> router raises a clear error.
    monkeypatch.setattr(settings, "ai_review_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", None)

    engine = CodeGenerationEngine(api_context.db)
    with pytest.raises(IntegrationError):
        engine.generate(
            engineering_request_id=uuid.UUID(request_id),
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
            materialization=_materialization(tmp_path),
        )


def test_company_rule_violation(api_context, monkeypatch, tmp_path) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    api_context.db.add(
        CompanyRule(
            organization_id=api_context.organization.id,
            name="No eval",
            description="eval is forbidden",
            rule_type=CompanyRuleType.FORBIDDEN_TEXT,
            pattern="eval(",
            severity=Severity.HIGH,
        )
    )
    api_context.db.commit()
    _mock_codegen(
        monkeypatch,
        {
            "changes": [
                {
                    "path": "backend/app/services/scan_service.py",
                    "operation": "modify",
                    "operations": [{"type": "insert", "content": "result = eval(payload)", "explanation": "x"}],
                    "explanation": "use eval",
                }
            ],
            "confidence_score": 0.9,
        },
    )
    engine = CodeGenerationEngine(api_context.db)
    with pytest.raises(AppError) as exc:
        engine.generate(
            engineering_request_id=uuid.UUID(request_id),
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
            materialization=_materialization(tmp_path),
        )
    assert "company rule" in str(exc.value).lower()


def test_architecture_rule_violation(api_context, monkeypatch, tmp_path) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    api_context.db.add(
        ArchitectureRule(
            organization_id=api_context.organization.id,
            name="API must not import models",
            description="layering",
            source_path_pattern="backend/app/api/*",
            forbidden_import_pattern=r"app\.models",
            severity=Severity.HIGH,
        )
    )
    api_context.db.commit()
    _mock_codegen(
        monkeypatch,
        {
            "changes": [
                {
                    "path": "backend/app/api/v1/foo.py",
                    "operation": "modify",
                    "operations": [
                        {"type": "insert", "content": "from app.models import User", "explanation": "x"}
                    ],
                    "explanation": "import models",
                }
            ],
            "confidence_score": 0.9,
        },
    )
    engine = CodeGenerationEngine(api_context.db)
    with pytest.raises(AppError) as exc:
        engine.generate(
            engineering_request_id=uuid.UUID(request_id),
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
            materialization=_materialization(tmp_path),
        )
    assert "architecture rule" in str(exc.value).lower()


def test_protected_files_rejected(api_context, monkeypatch, tmp_path) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    _mock_codegen(
        monkeypatch,
        {
            "changes": [
                {
                    "path": ".env",
                    "operation": "modify",
                    "operations": [{"type": "edit", "content": "SECRET=1", "explanation": "x"}],
                    "explanation": "edit env",
                }
            ],
            "confidence_score": 0.9,
        },
    )
    engine = CodeGenerationEngine(api_context.db)
    with pytest.raises(AppError) as exc:
        engine.generate(
            engineering_request_id=uuid.UUID(request_id),
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
            materialization=_materialization(tmp_path),
        )
    assert "protected files" in str(exc.value).lower()


def test_org_isolation(api_context, tmp_path) -> None:
    foreign = EngineeringRequest(
        organization_id=api_context.other_organization.id,
        title="Foreign request",
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

    engine = CodeGenerationEngine(api_context.db)
    with pytest.raises(NotFoundError):
        engine.generate(
            engineering_request_id=foreign.id,
            organization_id=api_context.organization.id,  # different org
            actor_user_id=api_context.user.id,
            materialization=_materialization(tmp_path),
        )


def test_deterministic_fallback(api_context, monkeypatch, tmp_path) -> None:
    request_id = _approved_request(api_context, monkeypatch)
    # AI returns nothing usable -> deterministic fallback from the approved plan.
    monkeypatch.setattr(CodeGenerationEngine, "_call_ai", lambda self, prompt: None)

    engine = CodeGenerationEngine(api_context.db)
    plan = engine.generate(
        engineering_request_id=uuid.UUID(request_id),
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        materialization=_materialization(tmp_path),
    )
    assert plan.ai_available is False
    assert plan.confidence_score == 0.3
    assert plan.files_to_modify == ["backend/app/services/scan_service.py"]
    assert plan.notes and "fallback" in plan.notes[0].lower()
