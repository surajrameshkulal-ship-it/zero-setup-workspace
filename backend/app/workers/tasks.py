from __future__ import annotations
import logging
import uuid
from typing import Callable

from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.services.dead_letter_service import DeadLetterScanService
from app.services.scan_service import PullRequestScanService

logger = logging.getLogger(__name__)


MAX_SCAN_RETRIES = 3


@celery_app.task(bind=True, name="scan.run_pr_scan", max_retries=MAX_SCAN_RETRIES)
def run_pr_scan(self, scan_id: str) -> str:
    return _run_pr_scan_with_retry(task=self, scan_id=scan_id)


def _run_pr_scan_with_retry(
    *,
    task,
    scan_id: str,
    session_factory: Callable = SessionLocal,
    service_factory: Callable = PullRequestScanService,
    dead_letter_service_factory: Callable = DeadLetterScanService,
) -> str:
    scan_uuid = uuid.UUID(scan_id)
    retries = int(getattr(task.request, "retries", 0) or 0)
    max_retries = int(getattr(task, "max_retries", MAX_SCAN_RETRIES) or MAX_SCAN_RETRIES)

    if retries > 0:
        logger.info(
            "scan_retry_attempt",
            extra={
                "scan_id": scan_id,
                "retry_attempt": retries,
                "max_retries": max_retries,
            },
        )

    db = session_factory()
    service = service_factory(db)
    try:
        service.run(scan_uuid, mark_failed_on_error=False)
        return scan_id
    except Exception as exc:
        if retries >= max_retries:
            logger.exception(
                "scan_retry_exhausted",
                extra={
                    "scan_id": scan_id,
                    "retry_attempt": retries,
                    "max_retries": max_retries,
                    "error": str(exc)[:500],
                },
            )
            failed_scan = service.mark_failed(scan_uuid, str(exc))
            try:
                dead_letter_service_factory().enqueue(
                    scan=failed_scan,
                    error_message=str(exc),
                    retry_count=retries,
                )
            except Exception:
                pass
            raise

        countdown = 2**retries
        next_retry = retries + 1
        logger.warning(
            "scan_retry_scheduled",
            extra={
                "scan_id": scan_id,
                "retry_attempt": next_retry,
                "max_retries": max_retries,
                "countdown_seconds": countdown,
                "error": str(exc)[:500],
            },
        )
        raise task.retry(exc=exc, countdown=countdown, max_retries=max_retries)
    finally:
        db.close()


@celery_app.task(name="workspace.launch_workspace_task")
def launch_workspace_task(workspace_id: str, *, session_factory: Callable = SessionLocal) -> str:
    """Run the real sandbox lifecycle for a created WorkspaceInstance.

    Idempotent and self-contained: the lifecycle service moves the instance
    through provisioning -> installing -> starting -> running and records any
    failure on the instance itself (it never raises out of the worker).
    """
    from app.services.workspace.workspace_lifecycle import WorkspaceLifecycleService

    db = session_factory()
    try:
        instance = WorkspaceLifecycleService(db).run(uuid.UUID(workspace_id))
        return instance.status
    except Exception as exc:  # noqa: BLE001 - never crash the worker
        logger.warning("launch_workspace_task_error", extra={"workspace_id": workspace_id, "error": str(exc)[:300]})
        return "failed"
    finally:
        db.close()
