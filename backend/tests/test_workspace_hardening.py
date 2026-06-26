from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.errors import AppError
from app.services.workspace.environment_spec_generator import EnvironmentSpecGenerator
from app.services.workspace.setup_intent_reader import SetupIntentReader
from app.services.workspace.workspace_builder import WorkspaceBuilder
from app.services.workspace.workspace_lifecycle import WorkspaceLifecycleService
from app.services.workspace.workspace_provisioner import WorkspaceProvisioner
from app.services.workspace.workspace_runtime import CommandResult, ProcessHandle

WS_BASE = "/api/v1/workspaces"

PY_FILES = {
    "pyproject.toml": '[project]\nrequires-python = ">=3.12"\ndependencies = ["fastapi", "uvicorn", "pytest"]\n',
    "requirements.txt": "fastapi\nuvicorn\npytest\n",
    "Dockerfile": "FROM python:3.12-slim\nEXPOSE 8000\nCMD uvicorn app.main:app\n",
    "README.md": "# api\nhealth at /health\n",
}


class FakeRunner:
    def __init__(self, *, install_ok=True):
        self.install_ok = install_ok

    def run(self, command, *, cwd, timeout, env=None):
        return CommandResult(0 if self.install_ok else 1, "ok", "" if self.install_ok else "boom")


class FakeProcess:
    def __init__(self, *, alive=True):
        self.alive = alive
        self.started = None
        self.terminated = []

    def start(self, command, *, cwd, env, log_path, cpu_limit=None, memory_mb=None):
        self.started = command
        Path(log_path).write_text("up\n", encoding="utf-8")
        return ProcessHandle(pid=4321, log_path=log_path)

    def is_running(self, pid):
        return self.alive

    def terminate(self, pid):
        self.terminated.append(pid)


class FakeProbe:
    def __init__(self, ready=True):
        self.ready = ready

    def wait(self, *, ports, health_command, cwd, timeout):
        return (self.ready, "ready" if self.ready else "timeout")


class FakeFetcher:
    def fetch(self, repository, dest):
        Path(dest, "README.md").write_text("x", encoding="utf-8")


def _provision(api_context):
    org, repo, user = api_context.organization.id, api_context.repository.id, api_context.user.id
    SetupIntentReader(api_context.db).generate(
        repository_id=repo, organization_id=org, actor_user_id=user, files=PY_FILES,
        file_tree=["pyproject.toml", "app/main.py"],
    )
    EnvironmentSpecGenerator(api_context.db).generate(repository_id=repo, organization_id=org, actor_user_id=user)
    WorkspaceBuilder(api_context.db).generate(repository_id=repo, organization_id=org, actor_user_id=user)
    WorkspaceProvisioner(api_context.db).generate(repository_id=repo, organization_id=org, actor_user_id=user)


def _service(api_context, **kw) -> WorkspaceLifecycleService:
    defaults = dict(runner=FakeRunner(), process_manager=FakeProcess(), probe=FakeProbe(), repo_fetcher=FakeFetcher())
    defaults.update(kw)
    return WorkspaceLifecycleService(api_context.db, **defaults)


def _create(api_context, service):
    return service.create(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )


# -- 1. concurrency guard -----------------------------------------------------


def test_concurrency_guard_returns_existing(api_context) -> None:
    _provision(api_context)
    service = _service(api_context)
    first = _create(api_context, service)
    second = _create(api_context, service)  # active -> deduplicated
    assert first.id == second.id
    assert len(service.list_for_repository(api_context.repository.id, api_context.organization.id)) == 1


def test_guard_allows_new_after_terminal(api_context) -> None:
    _provision(api_context)
    service = _service(api_context)
    first = _create(api_context, service)
    service.stop(first.id, api_context.organization.id, api_context.user.id)
    second = _create(api_context, service)  # previous is terminal -> new allowed
    assert first.id != second.id


# -- 2. structured timeline + durations + metrics -----------------------------


def test_timeline_events_and_durations(api_context) -> None:
    _provision(api_context)
    service = _service(api_context)
    instance = _create(api_context, service)
    result = service.run(instance.id)
    names = [e["event"] for e in result.events]
    for expected in ["Created", "Clone Started", "Clone Finished", "Install Started",
                     "Install Finished", "Runtime Started", "Health Passed", "Running"]:
        assert expected in names
    assert result.launch_duration_ms is not None
    assert result.install_duration_ms is not None
    assert result.startup_duration_ms is not None
    assert result.running_at and result.last_heartbeat_at
    service.delete(result.id, api_context.organization.id, api_context.user.id)


def test_metrics_aggregate(api_context) -> None:
    _provision(api_context)
    service = _service(api_context)
    run1 = service.run(_create(api_context, service).id)
    service.stop(run1.id, api_context.organization.id, api_context.user.id)
    # a second, failed launch
    service2 = _service(api_context, runner=FakeRunner(install_ok=False))
    service2.run(_create(api_context, service2).id)

    metrics = service.metrics(api_context.organization.id)
    assert metrics["total"] == 2
    assert metrics["average_launch_ms"] is not None  # from the successful run
    assert metrics["failure_reasons"]  # from the failed run
    assert metrics["by_status"].get("failed") == 1


# -- 3. restart ---------------------------------------------------------------


def test_restart_resets_same_instance(api_context) -> None:
    _provision(api_context)
    service = _service(api_context)
    instance = _create(api_context, service)
    running = service.run(instance.id)
    assert running.status == "running"
    restarted = service.restart(instance.id, api_context.organization.id, api_context.user.id)
    assert restarted.id == instance.id
    assert restarted.status == "pending"
    assert restarted.pid is None
    assert restarted.preview_url is None
    assert 4321 in service.process_manager.terminated
    assert any(e["event"] == "Restarted" for e in restarted.events)
    # it can run again
    again = service.run(instance.id)
    assert again.status == "running"
    service.delete(instance.id, api_context.organization.id, api_context.user.id)


# -- 4. cancellation ----------------------------------------------------------


def test_cancel_pending(api_context) -> None:
    _provision(api_context)
    service = _service(api_context)
    instance = _create(api_context, service)
    cancelled = service.cancel(instance.id, api_context.organization.id, api_context.user.id)
    assert cancelled.status == "cancelled"
    assert cancelled.cancel_requested is True
    assert any(e["event"] == "Cancelled" for e in cancelled.events)


def test_cancel_observed_during_run(api_context) -> None:
    _provision(api_context)
    service = _service(api_context)
    instance = _create(api_context, service)
    instance.cancel_requested = True  # flag set while still pending
    api_context.db.commit()
    result = service.run(instance.id)
    assert result.status == "cancelled"
    assert service.process_manager.started is None  # never started the runtime


def test_cancel_rejected_when_running(api_context) -> None:
    _provision(api_context)
    service = _service(api_context)
    running = service.run(_create(api_context, service).id)
    assert running.status == "running"
    with pytest.raises(AppError):
        service.cancel(running.id, api_context.organization.id, api_context.user.id)
    service.delete(running.id, api_context.organization.id, api_context.user.id)


# -- 5/6. heartbeat reconcile + crashed + auto-recovery -----------------------


def test_reconcile_marks_crashed_when_process_dead(api_context) -> None:
    _provision(api_context)
    proc = FakeProcess(alive=True)
    service = _service(api_context, process_manager=proc)
    running = service.run(_create(api_context, service).id)
    assert running.status == "running"
    proc.alive = False  # the sandbox process died
    summary = service.reconcile(organization_id=api_context.organization.id)
    assert summary["crashed"] == 1
    refreshed = service.get(running.id, api_context.organization.id)
    assert refreshed.status == "crashed"
    assert any(e["event"] == "Crashed" for e in refreshed.events)


def test_reconcile_updates_heartbeat_when_alive(api_context) -> None:
    _provision(api_context)
    proc = FakeProcess(alive=True)
    service = _service(api_context, process_manager=proc)
    running = service.run(_create(api_context, service).id)
    before = running.last_heartbeat_at
    summary = service.reconcile(organization_id=api_context.organization.id)
    assert summary["alive"] == 1
    assert service.get(running.id, api_context.organization.id).last_heartbeat_at >= before
    service.delete(running.id, api_context.organization.id, api_context.user.id)


def test_reconcile_reclaims_on_execution_timeout(api_context) -> None:
    _provision(api_context)
    proc = FakeProcess(alive=True)
    service = _service(api_context, process_manager=proc)
    running = service.run(_create(api_context, service).id)
    running.running_at = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
    api_context.db.commit()
    summary = service.reconcile(organization_id=api_context.organization.id)
    assert summary["reclaimed"] == 1
    refreshed = service.get(running.id, api_context.organization.id)
    assert refreshed.status == "crashed"
    assert "timeout" in (refreshed.error_message or "").lower()


def test_auto_recovery_restarts_once(api_context, monkeypatch) -> None:
    monkeypatch.setattr("app.services.workspace.workspace_lifecycle.settings.workspace_auto_recover", True)
    _provision(api_context)
    proc = FakeProcess(alive=False)  # process is dead -> crash -> recover
    service = _service(api_context, process_manager=proc)
    running = service.run(_create(api_context, service).id)
    summary = service.reconcile(organization_id=api_context.organization.id)
    assert summary["recovered"] == 1
    refreshed = service.get(running.id, api_context.organization.id)
    assert refreshed.recovery_attempts == 1
    assert refreshed.status == "running"
    service.delete(refreshed.id, api_context.organization.id, api_context.user.id)


# -- 8. cleanup job -----------------------------------------------------------


def test_cleanup_orphans_purges_terminal(api_context) -> None:
    _provision(api_context)
    service = _service(api_context)
    instance = _create(api_context, service)
    service.stop(instance.id, api_context.organization.id, api_context.user.id)
    removed = service.cleanup_orphans(ttl_seconds=0)  # everything terminal is "old"
    assert removed >= 1
    assert service.list_for_repository(api_context.repository.id, api_context.organization.id) == []


# -- 7. resource limits captured ----------------------------------------------


def test_resource_limits_recorded(api_context) -> None:
    _provision(api_context)
    service = _service(api_context)
    instance = _create(api_context, service)
    assert instance.cpu_limit is not None
    assert instance.memory_limit_mb is not None
    assert instance.execution_timeout_seconds > 0


# -- API surface --------------------------------------------------------------


def _no_enqueue(monkeypatch):
    monkeypatch.setattr("app.api.v1.workspaces._enqueue_launch", lambda *_a, **_k: None)


def test_api_restart_cancel_metrics(api_context, monkeypatch) -> None:
    _no_enqueue(monkeypatch)
    _provision(api_context)
    ws = api_context.client.post(f"{WS_BASE}/{api_context.repository.id}/launch").json()["id"]

    cancelled = api_context.client.post(f"{WS_BASE}/{ws}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    restarted = api_context.client.post(f"{WS_BASE}/{ws}/restart")
    assert restarted.status_code == 202
    assert restarted.json()["status"] == "pending"

    metrics = api_context.client.get(f"{WS_BASE}/metrics?repository_id={api_context.repository.id}")
    assert metrics.status_code == 200
    assert "by_status" in metrics.json()


def test_api_launch_dedup_returns_same(api_context, monkeypatch) -> None:
    _no_enqueue(monkeypatch)
    _provision(api_context)
    first = api_context.client.post(f"{WS_BASE}/{api_context.repository.id}/launch").json()["id"]
    second = api_context.client.post(f"{WS_BASE}/{api_context.repository.id}/launch").json()["id"]
    assert first == second
