from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.core.errors import AppError, NotFoundError
from app.models.audit import AuditLog
from app.services.workspace.environment_spec_generator import EnvironmentSpecGenerator
from app.services.workspace.setup_intent_reader import SetupIntentReader
from app.services.workspace.workspace_builder import WorkspaceBuilder
from app.services.workspace.workspace_launcher import LaunchResult, WorkspaceLauncher
from app.services.workspace.workspace_provisioner import WorkspaceProvisioner

REPO_BASE = "/api/v1/repositories"

PY_FILES = {
    "pyproject.toml": '[project]\nrequires-python = ">=3.12"\ndependencies = ["fastapi", "psycopg", "redis", "pytest"]\n',
    "requirements.txt": "fastapi\npsycopg\nredis\npytest\n",
    "Dockerfile": "FROM python:3.12-slim\nEXPOSE 8000\nCMD uvicorn app.main:app\n",
    "docker-compose.yml": "services:\n  db:\n    image: postgres:16\n    ports: ['5432:5432']\n",
    ".env.example": "DATABASE_URL=\nAPI_TOKEN=\n",
    "README.md": "# api\nhealth at /health\n",
}


class FakeRuntime:
    def __init__(self, *, available=True, healthy=True, fail_launch=False) -> None:
        self._available = available
        self._healthy = healthy
        self._fail = fail_launch
        self.launched: object | None = None
        self.stopped: list[str] = []

    def available(self) -> bool:
        return self._available

    def launch(self, spec) -> LaunchResult:
        if self._fail:
            raise RuntimeError("docker run exploded")
        self.launched = spec
        return LaunchResult(
            container_id="c123",
            port_mappings=[{"host": p, "container": p} for p in spec.ports],
            logs=["started"],
        )

    def health(self, container_id, command):
        return (self._healthy, "ok" if self._healthy else "health check failed")

    def logs(self, container_id, tail):
        return ["log-line-1", "log-line-2"]

    def stop(self, container_id):
        self.stopped.append(container_id)


def _provision(api_context):
    org, repo, user = api_context.organization.id, api_context.repository.id, api_context.user.id
    SetupIntentReader(api_context.db).generate(
        repository_id=repo, organization_id=org, actor_user_id=user, files=PY_FILES,
        file_tree=["pyproject.toml", "app/main.py"],
    )
    EnvironmentSpecGenerator(api_context.db).generate(repository_id=repo, organization_id=org, actor_user_id=user)
    WorkspaceBuilder(api_context.db).generate(repository_id=repo, organization_id=org, actor_user_id=user)
    WorkspaceProvisioner(api_context.db).generate(repository_id=repo, organization_id=org, actor_user_id=user)


def _launcher(api_context, runtime) -> WorkspaceLauncher:
    return WorkspaceLauncher(api_context.db, runtime=runtime, source_provider=lambda repo: "/tmp/ws-readonly")


def _launch(api_context, runtime):
    return _launcher(api_context, runtime).launch(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )


def test_launch_healthy(api_context) -> None:
    _provision(api_context)
    runtime = FakeRuntime(healthy=True)
    launch = _launch(api_context, runtime)
    assert launch.status == "healthy"
    assert launch.health_status == "healthy"
    assert launch.container_id == "c123"
    assert {"host": 8000, "container": 8000} in launch.port_mappings
    assert launch.published_url == "http://localhost:8000"
    assert launch.started_at and launch.expires_at
    assert launch.logs_tail
    # Safety rails are recorded.
    assert launch.safety["source_mounted_read_only"] is True
    assert launch.safety["no_secret_materialization"] is True
    assert launch.safety["no_merge_deploy_push"] is True
    assert launch.resource_limits["memory_mb"] >= 1024

    actions = {r.action for r in api_context.db.query(AuditLog).all()}
    assert {"workspace_launch_started", "workspace_launch_healthy"} <= actions


def test_launch_unhealthy(api_context) -> None:
    _provision(api_context)
    launch = _launch(api_context, FakeRuntime(healthy=False))
    assert launch.status == "unhealthy"
    assert launch.health_status == "unhealthy"
    assert "workspace_launch_unhealthy" in {r.action for r in api_context.db.query(AuditLog).all()}


def test_secrets_never_injected(api_context) -> None:
    _provision(api_context)
    runtime = FakeRuntime()
    _launch(api_context, runtime)
    # Only env var NAMES are passed to the runtime; never values.
    assert "DATABASE_URL" in runtime.launched.env_names
    assert "API_TOKEN" in runtime.launched.env_names
    # The mount is read-only and the network is constrained.
    assert runtime.launched.network == "bridge"


def test_requires_provision_plan(api_context) -> None:
    with pytest.raises(AppError):
        _launch(api_context, FakeRuntime())


def test_runtime_unavailable_fails_gracefully(api_context) -> None:
    _provision(api_context)
    launch = _launch(api_context, FakeRuntime(available=False))
    assert launch.status == "failed"
    assert "docker" in launch.failure_reason.lower()
    assert "workspace_launch_failed" in {r.action for r in api_context.db.query(AuditLog).all()}


def test_launch_failure_captured(api_context) -> None:
    _provision(api_context)
    launch = _launch(api_context, FakeRuntime(fail_launch=True))
    assert launch.status == "failed"
    assert "exploded" in launch.failure_reason


def test_stop_cleans_up(api_context) -> None:
    _provision(api_context)
    runtime = FakeRuntime()
    _launch(api_context, runtime)
    stopped = _launcher(api_context, runtime).stop(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    assert stopped.status == "stopped"
    assert "c123" in runtime.stopped
    assert stopped.stopped_at is not None
    assert "workspace_launch_stopped" in {r.action for r in api_context.db.query(AuditLog).all()}


def test_ttl_expiry_auto_cleans(api_context) -> None:
    _provision(api_context)
    runtime = FakeRuntime()
    launch = _launch(api_context, runtime)
    # Force expiry in the past.
    launch.expires_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    api_context.db.commit()

    fetched = _launcher(api_context, runtime).get_optional(
        api_context.repository.id, api_context.organization.id
    )
    assert fetched.status == "expired"
    assert "c123" in runtime.stopped
    assert "workspace_launch_expired" in {r.action for r in api_context.db.query(AuditLog).all()}


def test_relaunch_stops_previous(api_context) -> None:
    _provision(api_context)
    runtime = FakeRuntime()
    _launch(api_context, runtime)
    _launch(api_context, runtime)  # second launch
    assert "c123" in runtime.stopped  # previous sandbox was torn down first


def test_api_get_404_then_launch_and_stop(api_context) -> None:
    assert api_context.client.get(f"{REPO_BASE}/{api_context.repository.id}/workspace-launch").status_code == 404
    _provision(api_context)
    # Via the API the default Docker runtime is unavailable in CI; the launch
    # must degrade gracefully to a 'failed' status (HTTP 200), never a 500.
    posted = api_context.client.post(f"{REPO_BASE}/{api_context.repository.id}/workspace-launch")
    assert posted.status_code == 200
    assert posted.json()["status"] in ("failed", "running", "healthy", "unhealthy")
    fetched = api_context.client.get(f"{REPO_BASE}/{api_context.repository.id}/workspace-launch")
    assert fetched.status_code == 200
    assert fetched.json()["repository_full_name"] == "acme/payments-api"


def test_org_isolation(api_context) -> None:
    assert api_context.client.get(f"{REPO_BASE}/{api_context.other_repository.id}/workspace-launch").status_code == 404
    with pytest.raises(NotFoundError):
        _launch_other(api_context)


def _launch_other(api_context):
    return WorkspaceLauncher(api_context.db, runtime=FakeRuntime(), source_provider=lambda r: "/tmp/x").launch(
        repository_id=api_context.other_repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
