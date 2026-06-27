from __future__ import annotations

import uuid

from app.models.brain import BrainDecision, BrainRun
from app.models.engineering_request import EngineeringRequest, RequestPriority, RequestStatus, RequestType
from app.services.brain.brains import build_brains
from app.services.brain.memory_service import BrainMemoryService
from app.services.brain.safety_guard import BrainSafetyGuard
from app.services.brain.super_brain import (
    BrainContextBuilder,
    BrainRegistry,
    BrainReasoningService,
    BrainRouter,
    SuperBrainOrchestrator,
)

BRAIN_BASE = "/api/v1/brain"


def _failed_request(api_context, title="Broken thing"):
    req = EngineeringRequest(
        organization_id=api_context.organization.id,
        repository_id=api_context.repository.id,
        title=title,
        description="d",
        request_type=RequestType.BUG,
        status=RequestStatus.FAILED,
        priority=RequestPriority.HIGH,
    )
    api_context.db.add(req)
    api_context.db.commit()
    return req


# -- routing ------------------------------------------------------------------


def test_router_selects_relevant_brains() -> None:
    router = BrainRouter(BrainRegistry())
    debug_route = [b.name for b, _ in router.route("Why did the build fail? the sandbox crashed")]
    assert "debug" in debug_route or "workspace" in debug_route
    plan_route = [b.name for b, _ in router.route("plan the roadmap milestones and priorities")]
    assert "planning" in plan_route or "product" in plan_route


def test_router_always_answers_even_with_no_keywords() -> None:
    routed = BrainRouter(BrainRegistry()).route("zzzz qqqq")
    assert len(routed) >= 1  # falls back to product/planning


def test_can_handle_scores() -> None:
    brains = {b.name: b for b in build_brains()}
    assert brains["security"].can_handle("scan for security vulnerabilities") > 0
    assert brains["workspace"].can_handle("is the sandbox healthy") > 0


# -- context building ---------------------------------------------------------


def test_context_builder(api_context) -> None:
    ctx = BrainContextBuilder().build(api_context.db, api_context.organization.id)
    assert {"summary", "delivery", "blockers", "priorities"} <= set(ctx)
    assert isinstance(ctx["delivery"], dict)


# -- memory CRUD --------------------------------------------------------------


def test_memory_crud_and_search(api_context) -> None:
    svc = BrainMemoryService(api_context.db)
    m = svc.create(
        organization_id=api_context.organization.id,
        kind="decision",
        title="Chose PostgreSQL",
        content="We use PostgreSQL for durability.",
        tags=["db"],
    )
    assert m.id is not None
    listed = svc.list(api_context.organization.id)
    assert any(e.id == m.id for e in listed)
    found = svc.search(api_context.organization.id, ["postgresql"])
    assert any(e.id == m.id for e in found)


# -- secret redaction ---------------------------------------------------------


def test_safety_guard_redacts_secrets() -> None:
    guard = BrainSafetyGuard()
    assert "redacted" in guard.redact("api_key=sk-supersecretvalue1234567890ABCD")
    assert "ghp_" not in guard.redact("token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345")
    sanitized = guard.sanitize({"detail": "password=hunter2supersecretlong"})
    assert "hunter2supersecretlong" not in sanitized["detail"]


def test_ask_redacts_secret_in_question(api_context) -> None:
    run = SuperBrainOrchestrator(api_context.db).ask(
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        question="my key is ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345 what is the status?",
    )
    assert "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345" not in run.question


# -- reasoning + evidence + decisions -----------------------------------------


def test_ask_produces_evidence_and_decision(api_context) -> None:
    _failed_request(api_context, "Payment bug")
    run = SuperBrainOrchestrator(api_context.db).ask(
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        question="Why did things fail and what should we prioritize?",
    )
    assert run.status == "completed"
    assert run.primary_brain is not None
    assert run.brains_consulted
    assert run.evidence  # evidence-based
    assert run.confidence_score > 0
    assert run.steps  # per-brain steps recorded
    decisions = api_context.db.query(BrainDecision).filter(BrainDecision.run_id == run.id).all()
    assert decisions  # the recommendation is stored as an auditable decision


def test_ask_with_mocked_ai(api_context) -> None:
    reasoning = BrainReasoningService(ai_completer=lambda prompt: "MOCKED AI ANSWER")
    run = SuperBrainOrchestrator(api_context.db, reasoning=reasoning).ask(
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        question="What is the product status?",
    )
    assert run.answer == "MOCKED AI ANSWER"


def test_ask_deterministic_without_ai(api_context) -> None:
    run = SuperBrainOrchestrator(api_context.db).ask(
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        question="What is the product status?",
    )
    assert run.answer  # deterministic synthesis always yields an answer


# -- org isolation ------------------------------------------------------------


def test_org_isolation(api_context) -> None:
    other_run = BrainRun(
        organization_id=api_context.other_organization.id,
        question="secret other-org question",
        status="completed",
    )
    api_context.db.add(other_run)
    api_context.db.commit()
    from app.core.errors import NotFoundError
    import pytest

    with pytest.raises(NotFoundError):
        SuperBrainOrchestrator(api_context.db).get_run(other_run.id, api_context.organization.id)


# -- API ----------------------------------------------------------------------


def test_api_ask_and_reads(api_context) -> None:
    posted = api_context.client.post(f"{BRAIN_BASE}/ask", json={"question": "What should we work on next?"})
    assert posted.status_code == 200
    body = posted.json()
    assert body["answer"] and body["primary_brain"]
    run_id = body["id"]

    assert api_context.client.get(f"{BRAIN_BASE}/runs/{run_id}").status_code == 200
    convos = api_context.client.get(f"{BRAIN_BASE}/conversations")
    assert convos.status_code == 200 and len(convos.json()) >= 1
    convo_id = convos.json()[0]["id"]
    detail = api_context.client.get(f"{BRAIN_BASE}/conversations/{convo_id}")
    assert detail.status_code == 200
    assert any(m["role"] == "brain" for m in detail.json()["messages"])

    decisions = api_context.client.get(f"{BRAIN_BASE}/decisions")
    assert decisions.status_code == 200


def test_api_memory_crud(api_context) -> None:
    created = api_context.client.post(
        f"{BRAIN_BASE}/memory",
        json={"kind": "note", "title": "Design decision", "content": "Use Redis lock", "tags": ["infra"]},
    )
    assert created.status_code == 201
    listed = api_context.client.get(f"{BRAIN_BASE}/memory?query=redis")
    assert listed.status_code == 200
    assert any(m["title"] == "Design decision" for m in listed.json())
