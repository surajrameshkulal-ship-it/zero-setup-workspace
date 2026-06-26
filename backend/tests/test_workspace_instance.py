from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.errors import AppError, NotFoundError
from app.models.audit import AuditLog
from app.services.workspace.environment_spec_generator import EnvironmentSpecGenerator
from app.services.workspace.setup_intent_reader import SetupIntentReader
from app.services.workspace.workspace_builder import WorkspaceBuilder
from app.services.workspace.workspace_lifecycle import WorkspaceLifecycleService
from app.services.workspace.workspace_provisioner import WorkspaceProvisioner
from app.services.workspace.workspace_runtime import CommandResult, ProcessHandle, build_command_plan

WS_BASE = "/api/v1/workspaces"

PY_FILES = {
    "pyproject.toml": '[project]\nrequires-python = ">=3.12"\ndependencies = ["fastapi", "uvicorn", "pytest"]\n',
    "requirements.txt": "fastapi\nuvicorn\npytest\n",
    "README.md": "# api\nrun `uvicorn app.main:app`\nhealth at /health\n",
}


# -- fakes --------------------------------------------------------------------


class FakeRunner:
    def __init__(self, *, install_ok: bool = True) -> None:
        self.install_ok = install_ok
        self.calls: list[str] = []

    def run(self, command, *, cwd, timeout, env=None):
        self.calls.append(command)
        return CommandResult(0 if self.install_ok else 1, "installing deps...", "" if self.install_ok else "pip exploded")


class FakeProcess:
    def __init__(self) -> None:
        self.started: str | None = None
        self.terminated: list[int] = []

    def start(self, command, *, cwd, env, log_path, cpu_limit=None, memory_mb=None):
        self.started = command
        Path(log_path).write_text("server listening on port\n", encoding="utf-8")
        return ProcessHandle(pid=4321, log_path=log_path)

    def is_running(self, pid):
        return True

    def terminate(self, pid):
        self.terminated.append(pid)


class FakeProbe:
    def __init__(self, ready: bool = True) -> None:
        self.ready = ready

    def wait(self, *, ports, health_command, cwd, timeout):
        return (self.ready, "ready" if self.ready else "readiness timed out")


class FakeFetcher:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.fetched: str | None = None

    def fetch(self, repository, dest):
        if self.fail:
            raise AppError("Repository clone failed: boom")
        self.fetched = dest
        Path(dest, "README.md").write_text("# fetched", encoding="utf-8")


def _provision(api_context, files=PY_FILES, file_tree=None):
    org, repo, user = api_context.organization.id, api_context.repository.id, api_context.user.id
    SetupIntentReader(api_context.db).generate(
        repository_id=repo, organization_id=org, actor_user_id=user, files=files,
        file_tree=file_tree or ["pyproject.toml", "app/main.py"],
    )
    EnvironmentSpecGenerator(api_context.db).generate(repository_id=repo, organization_id=org, actor_user_id=user)
    WorkspaceBuilder(api_context.db).generate(repository_id=repo, organization_id=org, actor_user_id=user)
    WorkspaceProvisioner(api_context.db).generate(repository_id=repo, organization_id=org, actor_user_id=user)


def _service(api_context, **kw) -> WorkspaceLifecycleService:
    defaults = dict(runner=FakeRunner(), process_manager=FakeProcess(), probe=FakeProbe(), repo_fetcher=FakeFetcher())
    defaults.update(kw)
    return WorkspaceLifecycleService(api_context.db, **defaults)


def _create(api_context, service: WorkspaceLifecycleService):
    return service.create(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )


# -- command plan selection ---------------------------------------------------


def test_command_plan_selected_from_artifacts(api_context) -> None:
    _provision(api_context)
    from app.models.environment_spec import EnvironmentSpec
    from app.models.workspace_blueprint import WorkspaceBlueprint
    from app.models.workspace_provision_plan import WorkspaceProvisionPlan
    from sqlalchemy import select

    spec = api_context.db.scalar(select(EnvironmentSpec))
    bp = api_context.db.scalar(select(WorkspaceBlueprint))
    prov = api_context.db.scalar(select(WorkspaceProvisionPlan))
    plan = build_command_plan(prov, bp, spec)
    assert plan.install_command  # an install command was selected
    assert "uvicorn" in (plan.runtime_command or "")
    assert plan.exposed_ports == [8000]
    assert plan.runtime == "CPython"


# -- create -------------------------------------------------------------------


def test_create_requires_provision_plan(api_context) -> None:
    with pytest.raises(AppError):
        _create(api_context, _service(api_context))


def test_create_pending_instance(api_context) -> None:
    _provision(api_context)
    instance = _create(api_context, _service(api_context))
    assert instance.id is not None
    assert instance.status == "pending"
    assert instance.runtime_command and "uvicorn" in instance.runtime_command
    assert instance.exposed_ports == [8000]
    assert instance.provision_id is not None
    assert "workspace_instance_created" in {r.action for r in api_context.db.query(AuditLog).all()}


# -- run lifecycle ------------------------------------------------------------


def test_run_reaches_running(api_context) -> None:
    _provision(api_context)
    service = _service(api_context)
    instance = _create(api_context, service)
    runner: FakeRunner = service.runner  # type: ignore[assignment]
    process: FakeProcess = service.process_manager  # type: ignore[assignment]
    fetcher: FakeFetcher = service.repo_fetcher  # type: ignore[assignment]

    result = service.run(instance.id)
    assert result.status == "running"
    assert result.preview_url == "http://localhost:8000"
    assert result.pid == 4321
    assert fetcher.fetched is not None
    assert runner.calls  # install ran
    assert process.started and "uvicorn" in process.started
    assert any(e["stream"] == "start" for e in result.logs)
    actions = {r.action for r in api_context.db.query(AuditLog).all()}
    assert "workspace_instance_running" in actions

    # cleanup the real temp workspace
    service.delete(result.id, api_context.organization.id, api_context.user.id)


def test_run_failed_install(api_context) -> None:
    _provision(api_context)
    service = _service(api_context, runner=FakeRunner(install_ok=False))
    instance = _create(api_context, service)
    result = service.run(instance.id)
    assert result.status == "failed"
    assert "install failed" in (result.error_message or "").lower()
    assert service.process_manager.started is None  # never started the runtime
    service.delete(result.id, api_context.organization.id, api_context.user.id)


def test_run_failed_readiness_terminates_process(api_context) -> None:
    _provision(api_context)
    service = _service(api_context, probe=FakeProbe(ready=False))
    instance = _create(api_context, service)
    result = service.run(instance.id)
    assert result.status == "failed"
    assert "did not become ready" in (result.error_message or "")
    assert 4321 in service.process_manager.terminated  # process torn down
    assert result.pid is None
    service.delete(result.id, api_context.organization.id, api_context.user.id)


def test_run_failed_on_fetch_error(api_context) -> None:
    _provision(api_context)
    service = _service(api_context, repo_fetcher=FakeFetcher(fail=True))
    instance = _create(api_context, service)
    result = service.run(instance.id)
    assert result.status == "failed"
    assert "clone" in (result.error_message or "").lower()


def test_run_failed_when_no_start_command(api_context) -> None:
    # A repo with no recognizable manifests/extensions yields no start command.
    _provision(api_context, files={}, file_tree=["LICENSE"])
    service = _service(api_context)
    instance = _create(api_context, service)
    assert instance.runtime_command is None
    result = service.run(instance.id)
    assert result.status == "failed"
    assert "no start command" in (result.error_message or "").lower()
    assert service.process_manager.started is None


# -- stop / delete ------------------------------------------------------------


def test_stop_marks_stopped(api_context) -> None:
    _provision(api_context)
    service = _service(api_context)
    instance = _create(api_context, service)
    service.run(instance.id)
    stopped = service.stop(instance.id, api_context.organization.id, api_context.user.id)
    assert stopped.status == "stopped"
    assert stopped.stopped_at is not None
    assert 4321 in service.process_manager.terminated
    service.delete(instance.id, api_context.organization.id, api_context.user.id)


def test_delete_removes_record_and_dir(api_context) -> None:
    _provision(api_context)
    service = _service(api_context)
    instance = _create(api_context, service)
    result = service.run(instance.id)
    path = result.workspace_path
    assert path and Path(path).exists()
    service.delete(instance.id, api_context.organization.id, api_context.user.id)
    assert not Path(path).exists()
    with pytest.raises(NotFoundError):
        service.get(instance.id, api_context.organization.id)


# -- API ----------------------------------------------------------------------


def _no_enqueue(monkeypatch) -> None:
    # The Celery dispatch is an integration concern; stub it so tests never
    # contact a broker. The instance is created and left in 'pending'.
    monkeypatch.setattr("app.api.v1.workspaces._enqueue_launch", lambda *_a, **_k: None)


def test_api_launch_get_logs_and_404(api_context, monkeypatch) -> None:
    _no_enqueue(monkeypatch)
    _provision(api_context)
    posted = api_context.client.post(f"{WS_BASE}/{api_context.repository.id}/launch")
    assert posted.status_code == 202
    body = posted.json()
    assert body["status"] == "pending"  # worker not run in tests (no broker)
    workspace_id = body["id"]

    fetched = api_context.client.get(f"{WS_BASE}/{workspace_id}")
    assert fetched.status_code == 200
    assert fetched.json()["repository_full_name"] == "acme/payments-api"

    logs = api_context.client.get(f"{WS_BASE}/{workspace_id}/logs")
    assert logs.status_code == 200
    assert isinstance(logs.json()["logs"], list)

    listed = api_context.client.get(f"{WS_BASE}?repository_id={api_context.repository.id}")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    assert api_context.client.get(f"{WS_BASE}/{workspace_id.replace(workspace_id[0], '0', 1)}").status_code in (404, 422)


def test_api_stop_and_delete(api_context, monkeypatch) -> None:
    _no_enqueue(monkeypatch)
    _provision(api_context)
    workspace_id = api_context.client.post(f"{WS_BASE}/{api_context.repository.id}/launch").json()["id"]
    stopped = api_context.client.post(f"{WS_BASE}/{workspace_id}/stop")
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopped"
    deleted = api_context.client.delete(f"{WS_BASE}/{workspace_id}")
    assert deleted.status_code == 204
    assert api_context.client.get(f"{WS_BASE}/{workspace_id}").status_code == 404


def test_api_launch_requires_provision_plan(api_context) -> None:
    resp = api_context.client.post(f"{WS_BASE}/{api_context.repository.id}/launch")
    assert resp.status_code == 400


def test_org_isolation(api_context) -> None:
    assert api_context.client.post(f"{WS_BASE}/{api_context.other_repository.id}/launch").status_code == 404
    with pytest.raises(NotFoundError):
        _service(api_context).create(
            repository_id=api_context.other_repository.id,
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
        )
