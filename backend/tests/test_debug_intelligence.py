from __future__ import annotations

from app.models.workspace_instance import WorkspaceInstance
from app.services.brain.debug_intelligence import DebugIntelligenceService
from app.services.brain.failure_parsers import classify, parse
from app.services.brain.knowledge_service import KnowledgeGraphService

BASE = "/api/v1/brain/debug"

PYTEST_LOG = """============================= test session starts =============================
collected 3 items
tests/test_math.py::test_add FAILED
=================================== FAILURES ===================================
    def test_add():
>       assert add(1, 2) == 4
E       AssertionError: assert 3 == 4
tests/test_math.py:10: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_math.py::test_add - AssertionError: assert 3 == 4
"""

BUILD_LOG = """> next build
Failed to compile.
./src/app/page.tsx:12:5
Type error: Property 'foo' does not exist on type 'Props'.
"""

TRACEBACK_LOG = (
    'Traceback (most recent call last):\n'
    '  File "app/services/payments/processor.py", line 5, in run\n'
    '    charge()\n'
    '  File "app/services/payments/processor.py", line 9, in charge\n'
    '    raise ValueError("bad value")\n'
    'ValueError: bad value'
)

WORKSPACE_LOG = "Workspace did not become ready: readiness timed out after 60s. container exited 137"
CELERY_LOG = "[celery] Task app.workers.tasks.run_pr_scan[abcd] raised WorkerLostError: worker exited prematurely"
WEBHOOK_LOG = "Webhook signature verification failed: X-Hub-Signature-256 mismatch for delivery 123"
MIGRATION_LOG = "alembic.util.exc.CommandError: Target database is not up to date."
DEPENDENCY_LOG = "ModuleNotFoundError: No module named 'redis'"
AI_LOG = "groq.RateLimitError: rate limit exceeded for model llama-3.1"
LINT_LOG = "app/x.py:10:1: F401 'os' imported but unused [ruff]"


def _svc(api_context) -> DebugIntelligenceService:
    return DebugIntelligenceService(api_context.db)


def _diagnose(api_context, logs, source="manual"):
    return _svc(api_context).diagnose(organization_id=api_context.organization.id, logs=logs, source=source)


# -- classification / parsing -------------------------------------------------


def test_classify_all_types() -> None:
    assert classify(PYTEST_LOG) == "test_failure"
    assert classify(BUILD_LOG) == "build_failure"
    assert classify(TRACEBACK_LOG) == "runtime_error"
    assert classify(WORKSPACE_LOG, source_hint="workspace") == "workspace_failure"
    assert classify(CELERY_LOG) == "celery_error"
    assert classify(WEBHOOK_LOG) == "webhook_error"
    assert classify(MIGRATION_LOG) == "migration_error"
    assert classify(DEPENDENCY_LOG) == "dependency_error"
    assert classify(AI_LOG) == "ai_provider_error"
    assert classify(LINT_LOG) == "lint_failure"


def test_pytest_parser_extracts_test_and_file() -> None:
    parsed = parse(PYTEST_LOG, "test_failure")
    assert "tests/test_math.py::test_add" in parsed["failing_tests"]
    assert "tests/test_math.py" in parsed["affected_files"]
    assert "AssertionError" in parsed["error_message"]


def test_build_parser_extracts_file_and_message() -> None:
    parsed = parse(BUILD_LOG, "build_failure")
    assert any("page.tsx" in f for f in parsed["affected_files"])
    assert "does not exist" in parsed["error_message"]


def test_traceback_parser_finds_primary_frame() -> None:
    parsed = parse(TRACEBACK_LOG, "runtime_error")
    assert parsed["primary_file"] == "app/services/payments/processor.py"
    assert any(fr["func"] == "charge" for fr in parsed["frames"])
    assert parsed["error_message"].startswith("ValueError")


# -- diagnosis ----------------------------------------------------------------


def test_diagnose_test_failure(api_context) -> None:
    d = _diagnose(api_context, PYTEST_LOG)
    assert d.failure.failure_type == "test_failure"
    assert d.severity == "high"
    assert d.confidence_score > 0
    assert d.recommended_fix
    assert any(e["source"] == "test" for e in d.evidence)


def test_diagnose_maps_affected_services(api_context) -> None:
    d = _diagnose(api_context, TRACEBACK_LOG)
    assert "service:payments" in d.affected_services


def test_workspace_and_celery_and_webhook(api_context) -> None:
    assert _diagnose(api_context, WORKSPACE_LOG, source="workspace").failure.failure_type == "workspace_failure"
    assert _diagnose(api_context, CELERY_LOG).failure.failure_type == "celery_error"
    assert _diagnose(api_context, WEBHOOK_LOG).failure.failure_type == "webhook_error"


def test_root_cause_mapping_via_graph(api_context) -> None:
    KnowledgeGraphService(api_context.db).upsert_node(
        organization_id=api_context.organization.id, node_type="service", title="app.services.payments",
        source_type="service", source_id="app.services.payments", summary="payments processing",
    )
    api_context.db.commit()
    d = _diagnose(api_context, TRACEBACK_LOG)
    assert any("payments" in n["title"] for n in d.related_graph_nodes)


def test_secret_redaction(api_context) -> None:
    d = _diagnose(api_context, "Traceback...\nRuntimeError: token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345 leaked")
    assert "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345" not in d.failure.raw_log
    assert "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345" not in str(d.evidence)


def test_patterns_group_recurring(api_context) -> None:
    _diagnose(api_context, PYTEST_LOG)
    _diagnose(api_context, PYTEST_LOG)
    patterns = _svc(api_context).patterns(api_context.organization.id)
    assert patterns and patterns[0]["count"] == 2


def test_ingest_existing_failures(api_context) -> None:
    # A crashed workspace is ingested into a DebugFailure (read-only).
    ws = WorkspaceInstance(
        organization_id=api_context.organization.id, repository_id=api_context.repository.id,
        status="crashed", error_message="Workspace did not become ready",
    )
    api_context.db.add(ws)
    api_context.db.commit()
    result = _svc(api_context).ingest_failures(api_context.organization.id)
    assert result["ingested"] >= 1
    failures = _svc(api_context).list_failures(api_context.organization.id)
    assert any(f.source == "workspace" for f in failures)


def test_org_isolation(api_context) -> None:
    _svc(api_context).diagnose(organization_id=api_context.other_organization.id, logs=PYTEST_LOG)
    assert _svc(api_context).list_failures(api_context.organization.id) == []


def test_debug_brain_uses_diagnosis(api_context) -> None:
    from app.services.brain.super_brain import SuperBrainOrchestrator

    _diagnose(api_context, TRACEBACK_LOG)
    run = SuperBrainOrchestrator(api_context.db).ask(
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        question="Why did it fail and which file needs fixing?",
    )
    assert "debug" in run.brains_consulted
    assert any(e.get("source") in ("diagnosis", "affected_files") for e in run.evidence)


# -- API ----------------------------------------------------------------------


def test_api_debug_flow(api_context) -> None:
    posted = api_context.client.post(f"{BASE}/diagnose", json={"logs": PYTEST_LOG})
    assert posted.status_code == 200
    body = posted.json()
    assert body["failure"]["failure_type"] == "test_failure"
    assert body["recommended_fix"]
    failure_id = body["failure_id"]

    failures = api_context.client.get(f"{BASE}/failures")
    assert failures.status_code == 200 and len(failures.json()) >= 1

    detail = api_context.client.get(f"{BASE}/failures/{failure_id}")
    assert detail.status_code == 200
    assert "raw_log" in detail.json()

    patterns = api_context.client.get(f"{BASE}/patterns")
    assert patterns.status_code == 200
