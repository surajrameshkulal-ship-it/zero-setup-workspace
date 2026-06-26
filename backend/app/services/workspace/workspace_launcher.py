"""Workspace Launcher (Phase 11, Step 5 — Local sandbox launch).

Human-initiated: provisions and starts an isolated local container from the
Workspace Provision plan, health-checks it, and exposes logs.

Strong isolation is preserved even though we now run a container:
- Source is mounted READ-ONLY; secrets/.env/.git are never materialized and no
  secret values are ever injected (only variable names are known).
- CPU / memory / PID quotas and a TTL (auto-cleanup) are enforced.
- The sandbox NEVER merges, deploys, pushes, or modifies the real repository.
- The container runtime is behind an injectable driver so the orchestration is
  fully unit-tested without Docker; production uses the Docker CLI driver.
"""

from __future__ import annotations

import logging
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError
from app.models.environment_spec import EnvironmentSpec
from app.models.repository import Repository
from app.models.workspace_blueprint import WorkspaceBlueprint
from app.models.workspace_launch import WorkspaceLaunch
from app.models.workspace_provision_plan import WorkspaceProvisionPlan
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 3600
LOG_TAIL = 200


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class LaunchSpec:
    name: str
    image: str
    workspace_path: str
    start_command: str | None
    ports: list[int]
    env_names: list[str]
    cpu: float
    memory_mb: int
    pids_limit: int
    network: str


@dataclass
class LaunchResult:
    container_id: str
    port_mappings: list[dict]  # [{"host": int, "container": int}]
    logs: list[str] = field(default_factory=list)


class ContainerRuntime(Protocol):
    def available(self) -> bool: ...
    def launch(self, spec: LaunchSpec) -> LaunchResult: ...
    def health(self, container_id: str, command: str | None) -> tuple[bool, str]: ...
    def logs(self, container_id: str, tail: int) -> list[str]: ...
    def stop(self, container_id: str) -> None: ...


class DockerCliRuntime:
    """Production runtime backed by the Docker CLI, with isolation flags.

    Never enabled in tests (Docker is unavailable in CI/sandbox); orchestration
    is verified through an injected fake runtime instead.
    """

    def __init__(self, *, timeout: int = 120) -> None:
        self.timeout = timeout

    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(args, capture_output=True, text=True, timeout=self.timeout)

    def available(self) -> bool:
        try:
            return self._run(["docker", "version"]).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def launch(self, spec: LaunchSpec) -> LaunchResult:
        args = [
            "docker", "run", "-d", "--rm",
            "--name", spec.name,
            "--memory", f"{spec.memory_mb}m",
            "--cpus", str(spec.cpu),
            "--pids-limit", str(spec.pids_limit),
            "--network", spec.network,
            "--security-opt", "no-new-privileges",
            "--cap-drop", "ALL",
            # Read-only source mount — the sandbox cannot modify the repository.
            "-v", f"{spec.workspace_path}:/workspace:ro",
            "-w", "/workspace",
        ]
        port_mappings: list[dict] = []
        for port in spec.ports:
            args += ["-p", f"{port}:{port}"]
            port_mappings.append({"host": port, "container": port})
        # Secret values are never injected; only the image and start command run.
        args.append(spec.image)
        if spec.start_command:
            args += ["sh", "-lc", spec.start_command]
        proc = self._run(args)
        if proc.returncode != 0:
            raise AppError(f"Container launch failed: {proc.stderr.strip()[:500]}")
        return LaunchResult(container_id=proc.stdout.strip(), port_mappings=port_mappings)

    def health(self, container_id: str, command: str | None) -> tuple[bool, str]:
        if not command:
            return True, "No health command; assuming healthy if the container is running."
        proc = self._run(["docker", "exec", container_id, "sh", "-lc", command])
        ok = proc.returncode == 0
        return ok, (proc.stdout or proc.stderr).strip()[:500]

    def logs(self, container_id: str, tail: int) -> list[str]:
        proc = self._run(["docker", "logs", "--tail", str(tail), container_id])
        return (proc.stdout + proc.stderr).splitlines()[-tail:]

    def stop(self, container_id: str) -> None:
        self._run(["docker", "rm", "-f", container_id])


class WorkspaceLauncher:
    def __init__(
        self,
        db: Session,
        *,
        runtime: ContainerRuntime | None = None,
        source_provider=None,
    ) -> None:
        self.db = db
        self.audit = AuditService(db)
        self.runtime = runtime or DockerCliRuntime()
        # Returns a read-only workspace path for the repository. Defaults to the
        # secret-redacting RepositoryMaterializer; injectable for tests.
        self.source_provider = source_provider

    # -- queries ---------------------------------------------------------------

    def get_for_repository(self, repository_id: uuid.UUID, organization_id: uuid.UUID) -> WorkspaceLaunch:
        launch = self.get_optional(repository_id, organization_id)
        if not launch:
            raise NotFoundError("Workspace launch not found")
        return launch

    def get_optional(self, repository_id: uuid.UUID, organization_id: uuid.UUID) -> WorkspaceLaunch | None:
        launch = self.db.scalar(
            select(WorkspaceLaunch).where(
                WorkspaceLaunch.repository_id == repository_id,
                WorkspaceLaunch.organization_id == organization_id,
            )
        )
        if launch and self._is_expired(launch):
            self._expire(launch)
        return launch

    # -- commands --------------------------------------------------------------

    def launch(
        self,
        *,
        repository_id: uuid.UUID,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> WorkspaceLaunch:
        repository = self._require_repository(repository_id, organization_id)
        provision = self.db.scalar(
            select(WorkspaceProvisionPlan).where(
                WorkspaceProvisionPlan.repository_id == repository_id,
                WorkspaceProvisionPlan.organization_id == organization_id,
            )
        )
        if provision is None:
            raise AppError("No workspace provision plan found. Generate the provision plan first.")
        blueprint = self.db.scalar(
            select(WorkspaceBlueprint).where(
                WorkspaceBlueprint.repository_id == repository_id,
                WorkspaceBlueprint.organization_id == organization_id,
            )
        )
        spec = self.db.scalar(
            select(EnvironmentSpec).where(
                EnvironmentSpec.repository_id == repository_id,
                EnvironmentSpec.organization_id == organization_id,
            )
        )

        launch = self.db.scalar(
            select(WorkspaceLaunch).where(WorkspaceLaunch.repository_id == repository.id)
        )
        if launch is None:
            launch = WorkspaceLaunch(organization_id=organization_id, repository_id=repository.id)
            self.db.add(launch)

        # If a previous sandbox is still tracked as running, stop it first.
        if launch.container_id and launch.status in ("running", "healthy", "unhealthy"):
            self._safe_stop(launch.container_id)

        limits = self._resource_limits(provision, blueprint)
        ports = self._app_ports(provision, spec)
        image = self._image(provision, blueprint)
        start_command = (spec.dev_command if spec else None) or (spec.prod_command if spec else None) or (
            blueprint.startup_plan.get("start_sequence", [None])[0] if blueprint and blueprint.startup_plan else None
        )
        health_command = (spec.health_check_command if spec else None)

        launch.status = "launching"
        launch.runtime = blueprint.runtime if blueprint else (spec.runtime_name if spec else None)
        launch.image = image
        launch.start_command = start_command
        launch.ttl_seconds = ttl_seconds
        launch.resource_limits = limits
        launch.port_mappings = []
        launch.health_status = None
        launch.health_detail = None
        launch.logs_tail = []
        launch.failure_reason = None
        launch.stopped_at = None
        launch.safety = {
            "human_initiated": True,
            "source_mounted_read_only": True,
            "no_secret_materialization": True,
            "no_repository_modification": True,
            "no_merge_deploy_push": True,
            "resource_quotas_enforced": True,
            "ttl_seconds": ttl_seconds,
            "network": limits["network"],
            "org_isolated": True,
        }
        self.db.flush()

        self._audit(organization_id, actor_user_id, "workspace_launch_started", repository, {"image": image})

        try:
            if not self.runtime.available():
                return self._fail(launch, repository, organization_id, actor_user_id,
                                  "Container runtime (Docker) is not available on the host.")

            workspace_path = self._materialize(repository, organization_id, actor_user_id)

            result = self.runtime.launch(
                LaunchSpec(
                    name=f"codedna-ws-{repository.id}",
                    image=image,
                    workspace_path=workspace_path,
                    start_command=start_command,
                    ports=ports,
                    env_names=[e.get("name") for e in (spec.env_vars if spec else []) if isinstance(e, dict)],
                    cpu=limits["cpu"],
                    memory_mb=limits["memory_mb"],
                    pids_limit=limits["pids_limit"],
                    network=limits["network"],
                )
            )
            now = datetime.now(timezone.utc)
            launch.container_id = result.container_id
            launch.port_mappings = result.port_mappings
            launch.status = "running"
            launch.started_at = now.isoformat()
            launch.expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()
            if result.port_mappings:
                launch.published_url = f"http://localhost:{result.port_mappings[0]['host']}"

            ok, detail = self.runtime.health(result.container_id, health_command)
            launch.health_status = "healthy" if ok else "unhealthy"
            launch.health_detail = detail
            launch.status = "healthy" if ok else "unhealthy"
            try:
                launch.logs_tail = self.runtime.logs(result.container_id, LOG_TAIL)
            except Exception:  # noqa: BLE001 - logs are best-effort
                launch.logs_tail = result.logs

            self.db.flush()
            self._audit(
                organization_id, actor_user_id,
                "workspace_launch_healthy" if ok else "workspace_launch_unhealthy",
                repository, {"container_id": result.container_id, "health": launch.health_status},
            )
            self.db.commit()
            self.db.refresh(launch)
            logger.info("workspace_launch_complete", extra={"repository_id": str(repository.id), "status": launch.status})
            return launch
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            return self._fail(launch, repository, organization_id, actor_user_id, str(exc)[:500])

    def stop(
        self, *, repository_id: uuid.UUID, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None
    ) -> WorkspaceLaunch:
        launch = self.get_for_repository(repository_id, organization_id)
        if launch.container_id and launch.status in ("running", "healthy", "unhealthy"):
            self._safe_stop(launch.container_id)
        launch.status = "stopped"
        launch.health_status = None
        launch.stopped_at = _now_iso()
        self.db.flush()
        self._audit(organization_id, actor_user_id, "workspace_launch_stopped", launch.repository, {})
        self.db.commit()
        self.db.refresh(launch)
        return launch

    # -- helpers ---------------------------------------------------------------

    def _materialize(self, repository, organization_id, actor_user_id) -> str:
        if self.source_provider is not None:
            return self.source_provider(repository)
        # Production: read-only checkout with secret redaction.
        from app.services.agent.github_source_provider import GitHubTarballSourceProvider
        from app.services.workspace.repository_materializer import RepositoryMaterializer
        from app.services.workspace.secure_workspace_manager import SecureWorkspaceManager

        wm = SecureWorkspaceManager(db=self.db)
        snapshot = RepositoryMaterializer(self.db, workspace_manager=wm).materialize(
            repository_id=repository.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            target_branch=repository.default_branch,
            source_provider=GitHubTarballSourceProvider(self.db),
        )
        if not snapshot.materialized:
            raise AppError(f"Repository could not be materialized ({snapshot.reason}).")
        return snapshot.workspace_path

    @staticmethod
    def _resource_limits(provision: WorkspaceProvisionPlan, blueprint: WorkspaceBlueprint | None) -> dict:
        res = (blueprint.workspace_resources if blueprint else None) or {}
        return {
            "cpu": float(res.get("cpu", 1) or 1),
            "memory_mb": int(res.get("ram_mb", 1024) or 1024),
            "pids_limit": 256,
            # Bridge networking is required for the project to actually run; no
            # ports are published beyond the explicit app port mappings.
            "network": "bridge",
        }

    @staticmethod
    def _app_ports(provision: WorkspaceProvisionPlan, spec: EnvironmentSpec | None) -> list[int]:
        ports = list(getattr(spec, "app_ports", None) or [])
        if ports:
            return ports
        net = (provision.container_preparation or {}).get("network_plan", {}) if provision else {}
        return list(net.get("exposed_ports", []) or [])

    @staticmethod
    def _image(provision: WorkspaceProvisionPlan, blueprint: WorkspaceBlueprint | None) -> str:
        plan = (provision.container_preparation or {}).get("docker_image_plan", {}) if provision else {}
        image = plan.get("base_image")
        if image and image != "to be determined":
            return image
        return "alpine:3.20"  # minimal fallback; project runtime unknown

    def _fail(self, launch, repository, organization_id, actor_user_id, reason: str) -> WorkspaceLaunch:
        launch.status = "failed"
        launch.failure_reason = reason
        self.db.flush()
        self._audit(organization_id, actor_user_id, "workspace_launch_failed", repository, {"reason": reason})
        self.db.commit()
        self.db.refresh(launch)
        logger.warning("workspace_launch_failed", extra={"repository_id": str(repository.id), "reason": reason})
        return launch

    def _safe_stop(self, container_id: str) -> None:
        try:
            self.runtime.stop(container_id)
        except Exception:  # noqa: BLE001 - stop is best-effort
            logger.warning("workspace_launch_stop_failed", extra={"container_id": container_id})

    def _is_expired(self, launch: WorkspaceLaunch) -> bool:
        if launch.status not in ("running", "healthy", "unhealthy") or not launch.expires_at:
            return False
        try:
            return datetime.now(timezone.utc) > datetime.fromisoformat(launch.expires_at)
        except ValueError:
            return False

    def _expire(self, launch: WorkspaceLaunch) -> None:
        if launch.container_id:
            self._safe_stop(launch.container_id)
        launch.status = "expired"
        launch.health_status = None
        launch.stopped_at = _now_iso()
        self.db.flush()
        self._audit(launch.organization_id, None, "workspace_launch_expired", launch.repository, {})
        self.db.commit()
        self.db.refresh(launch)

    def _audit(self, organization_id, actor_user_id, action, repository, metadata) -> None:
        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type="repository",
            target_id=str(repository.id) if repository else None,
            metadata=metadata,
        )

    def _require_repository(self, repository_id: uuid.UUID, organization_id: uuid.UUID) -> Repository:
        repository = self.db.scalar(
            select(Repository).where(
                Repository.id == repository_id,
                Repository.organization_id == organization_id,
            )
        )
        if not repository:
            raise NotFoundError("Repository not found")
        return repository
