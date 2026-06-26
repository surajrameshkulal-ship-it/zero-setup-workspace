"""Workspace lifecycle service (Phase 11.1 — Real Sandbox Launch + hardening).

Turns a Workspace Provision plan into a real running sandbox and manages its full
lifecycle with: a per-repository concurrency guard + lock, restart, cancellation,
heartbeat/liveness reconciliation (crashed detection) with optional auto-recovery,
resource limits + execution timeout, an orphan cleanup job, a structured event
timeline, and per-instance + aggregate metrics.

Safe for local Docker/dev: the workspace lives under an isolated base directory
(SecureWorkspaceManager), commands run with timeouts, output is captured, and the
real repository is never modified (no GitHub writes).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, NotFoundError
from app.models.environment_spec import EnvironmentSpec
from app.models.repository import Repository
from app.models.workspace_instance import (
    ACTIVE_STATUSES,
    CANCELLABLE_STATUSES,
    TERMINAL_STATUSES,
    WorkspaceInstance,
)
from app.models.workspace_blueprint import WorkspaceBlueprint
from app.models.workspace_provision_plan import WorkspaceProvisionPlan
from app.services.audit_service import AuditService
from app.services.workspace.repo_fetcher import GitRepoFetcher
from app.services.workspace.secure_workspace_manager import SecureWorkspaceManager, WorkspaceHandle
from app.services.workspace.workspace_lock import WorkspaceLock
from app.services.workspace.workspace_runtime import (
    INSTALL_TIMEOUT_SECONDS,
    READINESS_TIMEOUT_SECONDS,
    LocalProcessManager,
    SubprocessCommandRunner,
    TcpReadinessProbe,
    build_command_plan,
)

logger = logging.getLogger(__name__)

MAX_LOG_ENTRIES = 500
MAX_EVENTS = 200
START_LOG_FILE = ".codedna-start.log"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _parse(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return None


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
        lock: WorkspaceLock | None = None,
    ) -> None:
        self.db = db
        self.audit = AuditService(db)
        self.runner = runner or SubprocessCommandRunner()
        self.process_manager = process_manager or LocalProcessManager()
        self.probe = probe or TcpReadinessProbe(self.runner)
        self.repo_fetcher = repo_fetcher
        self.workspace_manager = workspace_manager or SecureWorkspaceManager(db=db)
        self.lock = lock if lock is not None else WorkspaceLock()

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

    def active_for_repository(self, repository_id: uuid.UUID, organization_id: uuid.UUID) -> WorkspaceInstance | None:
        return self.db.scalar(
            select(WorkspaceInstance)
            .where(
                WorkspaceInstance.repository_id == repository_id,
                WorkspaceInstance.organization_id == organization_id,
                WorkspaceInstance.status.in_(ACTIVE_STATUSES),
            )
            .order_by(WorkspaceInstance.created_at.desc())
        )

    # -- create (with concurrency guard + lock) --------------------------------

    def create(
        self,
        *,
        repository_id: uuid.UUID,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        scan_id: uuid.UUID | None = None,
    ) -> WorkspaceInstance:
        repository = self._require_repository(repository_id, organization_id)

        acquired = self.lock.acquire(repository_id)
        try:
            # Concurrency guard: never create a duplicate launch for a repository.
            existing = self.active_for_repository(repository_id, organization_id)
            if existing is not None:
                logger.info(
                    "workspace_launch_deduplicated",
                    extra={"repository_id": str(repository_id), "workspace_id": str(existing.id), "status": existing.status},
                )
                return existing

            provision = self._fetch(WorkspaceProvisionPlan, repository_id, organization_id)
            if provision is None:
                raise AppError("No workspace provision plan found. Generate the provision plan first.")
            blueprint = self._fetch(WorkspaceBlueprint, repository_id, organization_id)
            spec = self._fetch(EnvironmentSpec, repository_id, organization_id)
            plan = build_command_plan(provision, blueprint, spec)

            resources = (blueprint.workspace_resources if blueprint else None) or {}
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
                cpu_limit=float(resources.get("cpu") or settings.workspace_default_cpu_limit),
                memory_limit_mb=int(resources.get("ram_mb") or settings.workspace_default_memory_mb),
                execution_timeout_seconds=settings.workspace_execution_timeout_seconds,
                logs=[{"stream": "system", "message": "Workspace launch requested."}],
                events=[],
            )
            self.db.add(instance)
            self.db.flush()
            self._emit(instance, "Created")
            self._audit(organization_id, actor_user_id, "workspace_instance_created", instance)
            self.db.commit()
            self.db.refresh(instance)
            return instance
        finally:
            if acquired:
                self.lock.release(repository_id)

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
        created_at = instance.created_at or _now()
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        try:
            if self._cancelled(instance):
                return self._cancel_now(instance)

            # 1) Provisioning.
            self._set_status(instance, "provisioning", "Preparing isolated workspace.")
            handle = self.workspace_manager.create_workspace(
                identifier=(repository.name if repository else "workspace"),
                organization_id=instance.organization_id,
            )
            instance.workspace_path = handle.path
            self._commit(instance)
            if self._cancelled(instance):
                return self._cancel_now(instance)

            # 2) Clone (read-only).
            self._emit(instance, "Clone Started")
            self._commit(instance)
            fetcher = self.repo_fetcher or GitRepoFetcher(self.db)
            fetcher.fetch(repository, handle.path)
            self._emit(instance, "Clone Finished")
            self._commit(instance)
            if self._cancelled(instance):
                return self._cancel_now(instance)

            # 3) Install.
            self._set_status(instance, "installing", f"Install: {plan.install_command or '(none)'}")
            self._emit(instance, "Install Started")
            install_start = _now()
            if plan.install_command:
                result = self.runner.run(plan.install_command, cwd=handle.path, timeout=INSTALL_TIMEOUT_SECONDS)
                self._log(instance, "install", result.stdout)
                if not result.ok:
                    self._log(instance, "install", result.stderr)
                    return self._fail(instance, f"Dependency install failed (exit {result.returncode}).")
            else:
                self._log(instance, "install", "No install command; skipping.")
            instance.install_duration_ms = int((_now() - install_start).total_seconds() * 1000)
            self._emit(instance, "Install Finished", f"{instance.install_duration_ms} ms")
            self._commit(instance)
            if self._cancelled(instance):
                return self._cancel_now(instance)

            # 4) Start runtime.
            if not plan.runtime_command:
                return self._fail(instance, "No start command could be determined from the provision plan.")
            self._set_status(instance, "starting", f"Start: {plan.runtime_command}")
            self._emit(instance, "Runtime Started")
            startup_start = _now()
            log_path = str(Path(handle.path) / START_LOG_FILE)
            env = {"PORT": str(plan.exposed_ports[0])} if plan.exposed_ports else None
            proc = self.process_manager.start(
                plan.runtime_command,
                cwd=handle.path,
                env=env,
                log_path=log_path,
                cpu_limit=instance.cpu_limit,
                memory_mb=instance.memory_limit_mb,
            )
            instance.pid = proc.pid
            self._commit(instance)

            # 5) Readiness.
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

            self._emit(instance, "Health Passed", detail)
            instance.startup_duration_ms = int((_now() - startup_start).total_seconds() * 1000)
            instance.launch_duration_ms = int((_now() - created_at).total_seconds() * 1000)
            instance.status = "running"
            instance.error_message = None
            instance.running_at = _now_iso()
            instance.last_heartbeat_at = _now_iso()
            instance.preview_url = (
                f"http://localhost:{plan.exposed_ports[0]}"
                if plan.exposed_ports
                else "(no exposed port; local preview unavailable)"
            )
            self._log(instance, "system", f"Workspace is running. {detail}")
            self._emit(instance, "Running", instance.preview_url)
            self._commit(instance)
            self._audit(instance.organization_id, None, "workspace_instance_running", instance)
            self.db.commit()
            logger.info("workspace_running", extra={"workspace_id": str(workspace_id), "url": instance.preview_url})
            return instance
        except Exception as exc:  # noqa: BLE001 - lifecycle must fail gracefully
            return self._fail(instance, f"Unexpected launch error: {str(exc)[:300]}")

    # -- stop / restart / cancel / delete --------------------------------------

    def stop(self, workspace_id: uuid.UUID, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> WorkspaceInstance:
        instance = self.get(workspace_id, organization_id)
        self._terminate(instance)
        instance.status = "stopped"
        instance.stopped_at = _now_iso()
        self._log(instance, "system", "Workspace stopped.")
        self._emit(instance, "Stopped")
        self._commit(instance)
        self._audit(organization_id, actor_user_id, "workspace_instance_stopped", instance)
        self.db.commit()
        self.db.refresh(instance)
        return instance

    def restart(self, workspace_id: uuid.UUID, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> WorkspaceInstance:
        """Stop the sandbox and re-run a fresh lifecycle on the same instance."""
        instance = self.get(workspace_id, organization_id)
        self._terminate(instance)
        # Reset to a clean pending state, preserving identity + selected commands.
        instance.status = "pending"
        instance.error_message = None
        instance.preview_url = None
        instance.workspace_path = None
        instance.pid = None
        instance.cancel_requested = False
        instance.running_at = None
        instance.stopped_at = None
        instance.install_duration_ms = None
        instance.startup_duration_ms = None
        instance.launch_duration_ms = None
        self._log(instance, "system", "Workspace restart requested.")
        self._emit(instance, "Restarted")
        self._commit(instance)
        self._audit(organization_id, actor_user_id, "workspace_instance_restarted", instance)
        self.db.commit()
        self.db.refresh(instance)
        return instance

    def cancel(self, workspace_id: uuid.UUID, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> WorkspaceInstance:
        instance = self.get(workspace_id, organization_id)
        if instance.status not in CANCELLABLE_STATUSES:
            raise AppError(
                f"Cannot cancel a workspace in '{instance.status}' state "
                f"(cancellable during: {', '.join(CANCELLABLE_STATUSES)})."
            )
        instance.cancel_requested = True
        self._terminate(instance)
        # If the worker hasn't started yet there is nothing to interrupt — finalize
        # immediately. Otherwise the running lifecycle observes the flag and aborts.
        instance.status = "cancelled"
        instance.stopped_at = _now_iso()
        self._log(instance, "system", "Workspace launch cancelled.")
        self._emit(instance, "Cancelled")
        self._commit(instance)
        self._audit(organization_id, actor_user_id, "workspace_instance_cancelled", instance)
        self.db.commit()
        self.db.refresh(instance)
        return instance

    def delete(self, workspace_id: uuid.UUID, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> None:
        instance = self.get(workspace_id, organization_id)
        self._terminate(instance)
        self._cleanup_dir(instance)
        self._audit(organization_id, actor_user_id, "workspace_instance_deleted", instance)
        self.db.delete(instance)
        self.db.commit()

    # -- heartbeat / reconcile / auto-recovery ---------------------------------

    def reconcile(self, *, organization_id: uuid.UUID | None = None) -> dict:
        """Refresh heartbeats for live sandboxes; mark dead ones crashed.

        Intended to run periodically (e.g. every 30s via Celery beat). A running
        instance whose process is no longer alive, or which has exceeded its
        execution timeout, is marked crashed; optional auto-recovery restarts it
        once.
        """
        query = select(WorkspaceInstance).where(WorkspaceInstance.status == "running")
        if organization_id is not None:
            query = query.where(WorkspaceInstance.organization_id == organization_id)
        summary = {"checked": 0, "alive": 0, "crashed": 0, "recovered": 0, "reclaimed": 0}
        for instance in self.db.scalars(query):
            summary["checked"] += 1
            alive = bool(instance.pid and self.process_manager.is_running(instance.pid))
            timed_out = self._execution_timed_out(instance)
            if alive and not timed_out:
                instance.last_heartbeat_at = _now_iso()
                self._commit(instance)
                summary["alive"] += 1
                continue
            reason = "Execution timeout exceeded." if timed_out else "Sandbox process is no longer alive (heartbeat lost)."
            self._terminate(instance)
            instance.status = "crashed"
            instance.error_message = reason
            instance.stopped_at = _now_iso()
            self._log(instance, "system", reason)
            self._emit(instance, "Crashed", reason)
            self._commit(instance)
            self._audit(instance.organization_id, None, "workspace_instance_crashed", instance, {"reason": reason})
            self.db.commit()
            summary["reclaimed" if timed_out else "crashed"] += 1
            if settings.workspace_auto_recover and instance.recovery_attempts < 1 and not timed_out:
                instance.recovery_attempts += 1
                self.restart(instance.id, instance.organization_id, None)
                self.run(instance.id)
                summary["recovered"] += 1
        return summary

    def cleanup_orphans(self, *, ttl_seconds: int | None = None) -> int:
        """Delete terminal workspace instances older than the configured TTL."""
        ttl = ttl_seconds if ttl_seconds is not None else settings.workspace_orphan_ttl_seconds
        cutoff = _now() - timedelta(seconds=ttl)
        stale = self.db.scalars(
            select(WorkspaceInstance).where(WorkspaceInstance.status.in_(TERMINAL_STATUSES))
        )
        removed = 0
        for instance in list(stale):
            updated = instance.updated_at
            if updated is not None and updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            if updated is not None and updated > cutoff:
                continue
            self._terminate(instance)
            self._cleanup_dir(instance)
            self.db.delete(instance)
            removed += 1
        if removed:
            self.db.commit()
        logger.info("workspace_orphans_cleaned", extra={"removed": removed, "ttl_seconds": ttl})
        return removed

    # -- metrics ---------------------------------------------------------------

    def metrics(self, organization_id: uuid.UUID, repository_id: uuid.UUID | None = None) -> dict:
        query = select(WorkspaceInstance).where(WorkspaceInstance.organization_id == organization_id)
        if repository_id is not None:
            query = query.where(WorkspaceInstance.repository_id == repository_id)
        rows = list(self.db.scalars(query))

        by_status: dict[str, int] = {}
        failures: dict[str, int] = {}
        launch, install, startup = [], [], []
        for r in rows:
            by_status[r.status] = by_status.get(r.status, 0) + 1
            if r.launch_duration_ms is not None:
                launch.append(r.launch_duration_ms)
            if r.install_duration_ms is not None:
                install.append(r.install_duration_ms)
            if r.startup_duration_ms is not None:
                startup.append(r.startup_duration_ms)
            if r.status in ("failed", "crashed") and r.error_message:
                failures[r.error_message] = failures.get(r.error_message, 0) + 1

        def _avg(values: list[int]) -> float | None:
            return round(sum(values) / len(values), 1) if values else None

        return {
            "total": len(rows),
            "by_status": by_status,
            "average_launch_ms": _avg(launch),
            "average_install_ms": _avg(install),
            "average_startup_ms": _avg(startup),
            "launched": len(launch),
            "failure_reasons": [
                {"reason": k, "count": v} for k, v in sorted(failures.items(), key=lambda kv: kv[1], reverse=True)
            ],
        }

    # -- helpers ---------------------------------------------------------------

    def _cancelled(self, instance: WorkspaceInstance) -> bool:
        # Re-read the flag so a cancel from another request/session is observed.
        self.db.refresh(instance, attribute_names=["cancel_requested"])
        return bool(instance.cancel_requested)

    def _cancel_now(self, instance: WorkspaceInstance) -> WorkspaceInstance:
        self._terminate(instance)
        instance.status = "cancelled"
        instance.stopped_at = _now_iso()
        self._log(instance, "system", "Workspace launch cancelled.")
        self._emit(instance, "Cancelled")
        self._commit(instance)
        self._audit(instance.organization_id, None, "workspace_instance_cancelled", instance)
        self.db.commit()
        return instance

    def _execution_timed_out(self, instance: WorkspaceInstance) -> bool:
        started = _parse(instance.running_at)
        if started is None:
            return False
        return _now() > started + timedelta(seconds=instance.execution_timeout_seconds)

    def _terminate(self, instance: WorkspaceInstance) -> None:
        if instance.pid:
            try:
                self.process_manager.terminate(instance.pid)
            except Exception:  # noqa: BLE001 - termination is best-effort
                logger.warning("workspace_terminate_failed", extra={"workspace_id": str(instance.id)})
            instance.pid = None

    def _cleanup_dir(self, instance: WorkspaceInstance) -> None:
        if not instance.workspace_path:
            return
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
            logger.warning("workspace_cleanup_skipped", extra={"workspace_id": str(instance.id), "reason": str(exc)})

    def _set_status(self, instance: WorkspaceInstance, status: str, message: str) -> None:
        instance.status = status
        self._log(instance, "system", message)

    def _emit(self, instance: WorkspaceInstance, event: str, detail: str | None = None) -> None:
        events = list(instance.events or [])
        events.append({"event": event, "at": _now_iso(), "detail": detail})
        instance.events = events[-MAX_EVENTS:]

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
        self._terminate(instance)
        instance.status = "failed"
        instance.error_message = reason
        instance.stopped_at = _now_iso()
        self._log(instance, "system", reason)
        self._emit(instance, "Failed", reason)
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
