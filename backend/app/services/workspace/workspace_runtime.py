"""Runtime collaborators for the real sandbox lifecycle (Phase 11, Step 5/11.1).

These small, injectable abstractions keep the lifecycle service fully testable
without actually cloning repositories, installing dependencies, or spawning
servers. Production implementations shell out to git / the shell and manage a
background process; tests inject fakes.

Safe-for-local-dev defaults: commands run with timeouts inside an isolated
workspace directory, stdout/stderr is captured, and nothing is run outside the
provided working directory.
"""

from __future__ import annotations

import logging
import os
import shlex
import signal
import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

INSTALL_TIMEOUT_SECONDS = 600
COMMAND_TIMEOUT_SECONDS = 300
READINESS_TIMEOUT_SECONDS = 60
READINESS_INTERVAL_SECONDS = 2


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass
class ProcessHandle:
    pid: int
    log_path: str | None = None


@dataclass
class CommandPlan:
    """Commands and ports selected from the provision/spec/blueprint artifacts."""

    install_command: str | None = None
    runtime_command: str | None = None
    health_command: str | None = None
    exposed_ports: list[int] = field(default_factory=list)
    runtime: str | None = None


# -- protocols ----------------------------------------------------------------


class RepoFetcher(Protocol):
    def fetch(self, repository, dest: str) -> None: ...


class CommandRunner(Protocol):
    def run(self, command: str, *, cwd: str, timeout: int, env: dict | None = None) -> CommandResult: ...


class ProcessManager(Protocol):
    def start(self, command: str, *, cwd: str, env: dict | None, log_path: str) -> ProcessHandle: ...
    def is_running(self, pid: int) -> bool: ...
    def terminate(self, pid: int) -> None: ...


class ReadinessProbe(Protocol):
    def wait(self, *, ports: list[int], health_command: str | None, cwd: str, timeout: int) -> tuple[bool, str]: ...


# -- default implementations --------------------------------------------------


def _split(command: str) -> list[str]:
    return shlex.split(command)


class SubprocessCommandRunner:
    """Runs a one-shot command (e.g. install) with a timeout, capturing output."""

    def run(self, command: str, *, cwd: str, timeout: int, env: dict | None = None) -> CommandResult:
        try:
            proc = subprocess.run(
                _split(command),
                cwd=cwd,
                env={**os.environ, **(env or {})},
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return CommandResult(proc.returncode, proc.stdout or "", proc.stderr or "")
        except subprocess.TimeoutExpired as exc:
            return CommandResult(124, exc.stdout or "", f"Command timed out after {timeout}s")
        except (OSError, ValueError) as exc:
            return CommandResult(127, "", str(exc))


class LocalProcessManager:
    """Starts a long-running command as a background process, logging to a file."""

    def start(self, command: str, *, cwd: str, env: dict | None, log_path: str) -> ProcessHandle:
        log_file = open(log_path, "ab", buffering=0)  # noqa: SIM115 - closed when process exits
        proc = subprocess.Popen(  # noqa: S603 - command is operator-selected, run in an isolated dir
            _split(command),
            cwd=cwd,
            env={**os.environ, **(env or {})},
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        return ProcessHandle(pid=proc.pid, log_path=log_path)

    def is_running(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def terminate(self, pid: int) -> None:
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except OSError:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass


class TcpReadinessProbe:
    """Considers the workspace ready when a port accepts a TCP connection.

    If a health command is provided it must also exit 0. With no signal at all
    we cannot confirm readiness and report failure rather than a false positive.
    """

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or SubprocessCommandRunner()

    def wait(self, *, ports: list[int], health_command: str | None, cwd: str, timeout: int) -> tuple[bool, str]:
        if not ports and not health_command:
            return False, "No exposed port or health command to verify readiness."
        deadline = time.monotonic() + timeout
        last = "not ready"
        while time.monotonic() < deadline:
            if ports and self._port_open(ports[0]):
                if health_command:
                    result = self.runner.run(health_command, cwd=cwd, timeout=30)
                    if result.ok:
                        return True, f"Port {ports[0]} open and health check passed."
                    last = f"Port open but health check failed: {result.stderr[:200]}"
                else:
                    return True, f"Port {ports[0]} is accepting connections."
            elif health_command and not ports:
                result = self.runner.run(health_command, cwd=cwd, timeout=30)
                if result.ok:
                    return True, "Health check passed."
                last = f"Health check failed: {result.stderr[:200]}"
            time.sleep(READINESS_INTERVAL_SECONDS)
        return False, f"Readiness timed out after {timeout}s ({last})."

    @staticmethod
    def _port_open(port: int, host: str = "127.0.0.1") -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            return sock.connect_ex((host, port)) == 0


# -- command plan selection ---------------------------------------------------


def build_command_plan(provision, blueprint, spec) -> CommandPlan:
    """Select install/runtime/health commands and ports from the artifacts.

    Priority: explicit Environment Spec commands, then the Workspace Provision
    dependency/startup plan, then the Workspace Blueprint startup sequences.
    """
    plan = CommandPlan(runtime=getattr(blueprint, "runtime", None) or getattr(spec, "runtime_name", None))

    # Install command.
    if spec and getattr(spec, "install_command", None):
        plan.install_command = spec.install_command
    elif provision and (provision.dependency_plan or []):
        for step in provision.dependency_plan:
            cmd = step.get("command") if isinstance(step, dict) else None
            if cmd and step.get("status") == "planned":
                plan.install_command = cmd
                break
    if not plan.install_command and blueprint:
        seq = (blueprint.startup_plan or {}).get("install_sequence") or []
        plan.install_command = _first_real(seq)

    # Runtime / start command.
    if spec and (getattr(spec, "dev_command", None) or getattr(spec, "prod_command", None)):
        plan.runtime_command = spec.dev_command or spec.prod_command
    if not plan.runtime_command and blueprint:
        seq = (blueprint.startup_plan or {}).get("start_sequence") or []
        plan.runtime_command = _first_real(seq)
    if not plan.runtime_command and provision:
        for phase in provision.startup_plan or []:
            if isinstance(phase, dict) and phase.get("phase") == "Prepare application":
                plan.runtime_command = _first_real(phase.get("actions") or [])
                break

    # Health command.
    plan.health_command = getattr(spec, "health_check_command", None)

    # Exposed ports.
    if spec and getattr(spec, "app_ports", None):
        plan.exposed_ports = [int(p) for p in spec.app_ports]
    elif provision:
        net = (provision.container_preparation or {}).get("network_plan", {})
        plan.exposed_ports = [int(p) for p in (net.get("exposed_ports") or [])]

    return plan


def _first_real(steps) -> str | None:
    for step in steps or []:
        if isinstance(step, str) and step.strip() and not step.lower().startswith("no "):
            return step
    return None
