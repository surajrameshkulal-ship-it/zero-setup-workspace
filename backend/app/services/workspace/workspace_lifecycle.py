"""Workspace lifecycle service (Phase 11, Step 5 / 11.1 — Real Sandbox Launch).

Turns a Workspace Provision plan into a real running sandbox: fetch the repo
into an isolated workspace, install dependencies, start the runtime command,
probe readiness, and capture logs — moving the instance through
pending -> provisioning -> installing -> starting -> running (or failed).

Safe for local Docker/dev: the workspace lives under an isolated base directory
(SecureWorkspaceManager), commands run with timeouts, stdout/stderr is captured,
failures are graceful with a clear reason, and nothing outside the workspace is
touched. No GitHub writes; the real repository is never modified.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError
from app.models.environment_spec import EnvironmentSpec
from app.models.repository import Repository
from app.models.workspace_blueprint import WorkspaceBlueprint
from app.models.workspace_instance import WorkspaceInstance
from app.models.workspace_provision_plan import WorkspaceProvisionPlan
from app.services.audit_service import AuditService
from app.services.workspace.repo_fetcher import GitRepoFetcher
from app.services.workspace.secure_workspace_manager import SecureWorkspaceManager, WorkspaceHandle
from app.services.workspace.workspace_runtime import (
    INSTALL_TIMEOUT_SECONDS,
    READINESS_TIMEOUT_SECONDS,
    CommandPlan,
    LocalProcessManager,
    SubprocessCommandRunner,
    TcpReadinessProbe,
    build_command_plan,
)

logger = logging.getLogger(__name__)

MAX_LOG_ENTRIES = 500
START_LOG_FILE = ".codedna-start.log"


class WorkspaceLifecycleService:
    def __init__(
        self,
        db: Session,
        *,
        runner=None,
        process_manager=None,
        probe=None,
        repo_fetcher=None,
        workspace_manager: SecureWorkspaceManager | None = None,
    ) -> None:
        self.db = db
        self.audit = AuditService(db)
        self.runner = runner or SubprocessCommandRunner()
        self.process_manager = process_manager or LocalProcessManager()
        self.probe = probe or TcpReadinessProbe(self.runner)
        self.repo_fetcher = repo_fetcher  # default constructed lazily (needs db)
        self.workspace_manager = workspace_manager or SecureWorkspaceManager(db=db)

    # -- queries ---------------------------------------------------------------

    def get(self, workspace_id: uuid.UUID, organization_id: uuid.UUID) -> WorkspaceInstance:
        instance = self.db.scalar(
            select(WorkspaceInstance).where(
                WorkspaceInstance.id == workspace_id,
                WorkspaceInstance.organization_id == organization_id,
            )
        )
        if not instance:
            raise NotFoundError("Workspace instance not found")
        return instance

    def list_for_repository(self, repository_id: uuid.UUID, organization_id: uuid.UUID) -> list[WorkspaceInstance]:
        return list(
            self.db.scalars(
                select(WorkspaceInstance)
                .where(
                    WorkspaceInstance.repository_id == repository_id,
                    WorkspaceInstance.organization_id == organization_id,
                )
                .order_by(WorkspaceInstance.created_at.desc())
            )
        )

    # -- create ----------------------------------------------------------------

    def create(
        self,
        *,
        repository_id: uuid.UUID,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        scan_id: uuid.UUID | None = None,
    ) -> WorkspaceInstance:
        repository = self._require_repository(repository_id, organization_id)
        provision = self._fetch(WorkspaceProvisionPlan, repository_id, organization_id)
        if provision is None:
            raise AppError("No workspace provision plan found. Generate the provision plan first.")
        blueprint = self._fetch(WorkspaceBlueprint, repository_id, organization_id)
        spec = self._fetch(EnvironmentSpec, repository_id, organization_id)

        plan = build_command_plan(provision, blueprint, spec)

        instance = WorkspaceInstance(
            organization_id=organization_id,
            repository_id=repository.id,
            scan_id=scan_id,
            environment_spec_id=getattr(spec, "id", None),
            blueprint_id=getattr(blueprint, "id", None),
            provision_id=provision.id,
            status="pending",
            runtime=plan.runtime,
            install_command=plan.install_command,
            runtime_command=plan.runtime_command,
            exposed_ports=plan.exposed_ports,
            logs=[{"stream": "system", "message": "Workspace launch requested."}],
        )
        self.db.add(instance)
        self.db.flush()
        self._audit(organization_id, actor_user_id, "workspace_instance_created", instance)
        self.db.commit()
        self.db.refresh(instance)
        return instance

    # -- run (worker) ----------------------------------------------------------

    def run(self, workspace_id: uuid.UUID) -> WorkspaceInstance:
        instance = self.db.get(WorkspaceInstance, workspace_id)
        if instance is None:
            raise NotFoundError("Workspace instance not found")
        if instance.status != "pending":
            logger.info("workspace_run_skipped", extra={"workspace_id": str(workspace_id), "status": instance.status})
            return instance

        repository = self.db.get(Repository, instance.repository_id)
        provision = self.db.get(WorkspaceProvisionPlan, instance.provision_id) if instance.provision_id else None
        blueprint = self.db.get(WorkspaceBlueprint, instance.blueprint_id) if instance.blueprint_id else None
        spec = self.db.get(EnvironmentSpec, instance.environment_spec_id) if instance.environment_spec_id else None
        plan = build_command_plan(provision, blueprint, spec)

        try:
            # 1) Provisioning: isolated workspace directory.
            self._set_status(instance, "provisioning", "Preparing isolated workspace.")
            handle = self.workspace_manager.create_workspace(
                identifier=(repository.name if repository else "workspace"),
                organization_id=instance.organization_id,
            )
            instance.workspace_path = handle.path
            self._commit(instance)

            # 2) Fetch repository (read-only) into the workspace.
            self._log(instance, "system", "Fetching repository into workspace.")
            self._commit(instance)
            fetcher = self.repo_fetcher or GitRepoFetcher(self.db)
            fetcher.fetch(repository, handle.path)

            # 3) Install dependencies.
            self._set_status(instance, "installing", f"Install: {plan.install_command or '(none)'}")
            if plan.install_command:
                result = self.runner.run(plan.install_command, cwd=handle.path, timeout=INSTALL_TIMEOUT_SECONDS)
                self._log(instance, "install", result.stdout)
                if not result.ok:
                    self._log(instance, "install", result.stderr)
                    return self._fail(instance, f"Dependency install failed (exit {result.returncode}).")
            else:
                self._log(instance, "install", "No install command; skipping.")
            self._commit(instance)

            # 4) Start the runtime command as a background process.
            if not plan.runtime_command:
                return self._fail(instance, "No start command could be determined from the provision plan.")
            self._set_status(instance, "starting", f"Start: {plan.runtime_command}")
            log_path = str(Path(handle.path) / START_LOG_FILE)
            env = {"PORT": str(plan.exposed_ports[0])} if plan.exposed_ports else None
            proc = self.process_manager.start(plan.runtime_command, cwd=handle.path, env=env, log_path=log_path)
            instance.pid = proc.pid
            self._commit(instance)

            # 5) Readiness probe.
            ready, detail = self.probe.wait(
                ports=plan.exposed_ports,
                health_command=plan.health_command,
                cwd=handle.path,
                timeout=READINESS_TIMEOUT_SECONDS,
            )
            self._append_start_log(instance, log_path)
            if not ready:
                self.process_manager.terminate(proc.pid)
                instance.pid = None
                return self._fail(instance, f"Workspace did not become ready: {detail}")

            instance.status = "running"
            instance.error_message = None
            if plan.exposed_ports:
                instance.preview_url = f"http://localhost:{plan.exposed_ports[0]}"
            else:
                instance.preview_url = "(no exposed port; local preview unavailable)"
            self._log(instance, "system", f"Workspace is running. {detail}")
            self._commit(instance)
            self._audit(instance.organization_id, None, "workspace_instance_running", instance)
            self.db.commit()
            logger.info("workspace_running", extra={"workspace_id": str(workspace_id), "url": instance.preview_url})
            return instance
        except Exception as exc:  # noqa: BLE001 - lifecycle must fail gracefully
            return self._fail(instance, f"Unexpected launch error: {str(exc)[:300]}")

    # -- stop / delete ---------------------------------------------------------

    def stop(self, workspace_id: uuid.UUID, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> WorkspaceInstance:
        instance = self.get(workspace_id, organization_id)
        if instance.pid:
            self.process_manager.terminate(instance.pid)
            instance.pid = None
        instance.status = "stopped"
        instance.stopped_at = _now_iso()
        self._log(instance, "system", "Workspace stopped.")
        self._commit(instance)
        self._audit(organization_id, actor_user_id, "workspace_instance_stopped", instance)
        self.db.commit()
        self.db.refresh(instance)
        return instance

    def delete(self, workspace_id: uuid.UUID, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> None:
        instance = self.get(workspace_id, organization_id)
        if instance.pid:
            self.process_manager.terminate(instance.pid)
            instance.pid = None
        if instance.workspace_path:
            try:
                handle = WorkspaceHandle(
                    workspace_id=str(instance.id),
                    path=instance.workspace_path,
                    branch_name=None,
                    base_branch=None,
                    max_bytes=self.workspace_manager.max_bytes,
                )
                self.workspace_manager.cleanup(handle)
            except AppError as exc:
                logger.warning("workspace_cleanup_skipped", extra={"workspace_id": str(workspace_id), "reason": str(exc)})
        self._audit(organization_id, actor_user_id, "workspace_instance_deleted", instance)
        self.db.delete(instance)
        self.db.commit()

    # -- helpers ---------------------------------------------------------------

    def _set_status(self, instance: WorkspaceInstance, status: str, message: str) -> None:
        instance.status = status
        self._log(instance, "system", message)

    def _log(self, instance: WorkspaceInstance, stream: str, message: str | None) -> None:
        if not message:
            return
        entries = list(instance.logs or [])
        for line in str(message).splitlines() or [str(message)]:
            if line.strip() == "":
                continue
            entries.append({"stream": stream, "message": line})
        instance.logs = entries[-MAX_LOG_ENTRIES:]

    def _append_start_log(self, instance: WorkspaceInstance, log_path: str) -> None:
        try:
            text = Path(log_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        self._log(instance, "start", text[-8000:])

    def _fail(self, instance: WorkspaceInstance, reason: str) -> WorkspaceInstance:
        instance.status = "failed"
        instance.error_message = reason
        self._log(instance, "system", reason)
        self._commit(instance)
        self._audit(instance.organization_id, None, "workspace_instance_failed", instance, {"reason": reason})
        self.db.commit()
        logger.warning("workspace_failed", extra={"workspace_id": str(instance.id), "reason": reason})
        return instance

    def _commit(self, instance: WorkspaceInstance) -> None:
        self.db.flush()
        self.db.commit()
        self.db.refresh(instance)

    def _audit(self, organization_id, actor_user_id, action, instance, metadata=None) -> None:
        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type="workspace_instance",
            target_id=str(instance.id),
            metadata=metadata or {"status": instance.status},
        )

    def _fetch(self, model, repository_id: uuid.UUID, organization_id: uuid.UUID):
        return self.db.scalar(
            select(model).where(model.repository_id == repository_id, model.organization_id == organization_id)
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
