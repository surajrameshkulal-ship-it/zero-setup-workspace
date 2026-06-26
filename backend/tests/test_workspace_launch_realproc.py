"""Real end-to-end launch validation (Phase 11 Step 5.1).

Drives the WorkspaceLifecycleService with the REAL subprocess runner, process
manager, and TCP readiness probe — launching a genuine local HTTP server — so we
exercise the actual run/stop/delete path without Docker or GitHub. A fake repo
fetcher stands in for the read-only clone (the only network-bound collaborator).
"""

from __future__ import annotations

import socket
import sys
import time
from pathlib import Path

import pytest

from app.services.workspace.environment_spec_generator import EnvironmentSpecGenerator
from app.services.workspace.setup_intent_reader import SetupIntentReader
from app.services.workspace.workspace_builder import WorkspaceBuilder
from app.services.workspace.workspace_lifecycle import WorkspaceLifecycleService
from app.services.workspace.workspace_provisioner import WorkspaceProvisioner
from app.services.workspace.workspace_runtime import CommandPlan

PY = sys.executable


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


class FakeFetcher:
    """Stands in for the read-only GitHub clone by writing a tiny local app."""

    def fetch(self, repository, dest):
        Path(dest, "index.html").write_text("<h1>codedna sandbox ok</h1>", encoding="utf-8")


def _provision(api_context):
    org, repo, user = api_context.organization.id, api_context.repository.id, api_context.user.id
    SetupIntentReader(api_context.db).generate(
        repository_id=repo, organization_id=org, actor_user_id=user,
        files={"index.html": "<h1>hi</h1>"}, file_tree=["index.html", "style.css", "app.js"],
    )
    EnvironmentSpecGenerator(api_context.db).generate(repository_id=repo, organization_id=org, actor_user_id=user)
    WorkspaceBuilder(api_context.db).generate(repository_id=repo, organization_id=org, actor_user_id=user)
    WorkspaceProvisioner(api_context.db).generate(repository_id=repo, organization_id=org, actor_user_id=user)


def test_real_launch_lifecycle_running_then_stop_then_delete(api_context, monkeypatch) -> None:
    port = _free_port()
    plan = CommandPlan(
        install_command=f"{PY} -V",
        runtime_command=f"{PY} -m http.server {port}",
        health_command=None,
        exposed_ports=[port],
        runtime="CPython",
    )
    monkeypatch.setattr(
        "app.services.workspace.workspace_lifecycle.build_command_plan", lambda *_a, **_k: plan
    )
    _provision(api_context)

    service = WorkspaceLifecycleService(api_context.db, repo_fetcher=FakeFetcher())
    instance = service.create(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    assert instance.status == "pending"

    result = service.run(instance.id)

    # --- evidence ---
    print("\n==== REAL LAUNCH EVIDENCE ====")
    print("final status:", result.status)
    print("preview_url:", result.preview_url)
    print("exposed_ports:", result.exposed_ports)
    print("runtime_command:", result.runtime_command)
    print("pid set:", result.pid is not None)
    print("port actually open:", _port_open(port))
    print("log streams:", sorted({e["stream"] for e in result.logs}))
    for e in result.logs[-8:]:
        print(f"  [{e['stream']}] {e['message']}")

    assert result.status == "running"
    assert result.preview_url == f"http://localhost:{port}"
    assert result.exposed_ports == [port]
    assert _port_open(port) is True  # a real server is genuinely listening
    assert any(e["stream"] == "system" for e in result.logs)

    # stop tears the real process down
    stopped = service.stop(result.id, api_context.organization.id, api_context.user.id)
    print("after stop -> status:", stopped.status)
    deadline = time.monotonic() + 5
    while _port_open(port) and time.monotonic() < deadline:
        time.sleep(0.2)
    print("port open after stop:", _port_open(port))
    assert stopped.status == "stopped"
    assert _port_open(port) is False  # process really terminated

    # delete removes the workspace directory
    path = result.workspace_path
    assert path and Path(path).exists()
    service.delete(result.id, api_context.organization.id, api_context.user.id)
    print("workspace dir exists after delete:", Path(path).exists())
    assert not Path(path).exists()


def test_real_launch_failure_has_clear_error(api_context, monkeypatch, capsys) -> None:
    # A start command that exits immediately and never opens the port -> the
    # readiness probe fails and the instance reports a clear error_message.
    port = _free_port()
    monkeypatch.setattr("app.services.workspace.workspace_lifecycle.READINESS_TIMEOUT_SECONDS", 5)
    plan = CommandPlan(
        install_command=f"{PY} -V",
        runtime_command=f"{PY} -c \"raise SystemExit(1)\"",
        health_command=None,
        exposed_ports=[port],
        runtime="CPython",
    )
    monkeypatch.setattr(
        "app.services.workspace.workspace_lifecycle.build_command_plan", lambda *_a, **_k: plan
    )
    _provision(api_context)

    service = WorkspaceLifecycleService(api_context.db, repo_fetcher=FakeFetcher())
    instance = service.create(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    result = service.run(instance.id)

    print("\n==== REAL LAUNCH FAILURE EVIDENCE ====")
    print("final status:", result.status)
    print("error_message:", result.error_message)

    assert result.status == "failed"
    assert result.error_message and "did not become ready" in result.error_message
    assert result.pid is None  # process was cleaned up
    service.delete(result.id, api_context.organization.id, api_context.user.id)
