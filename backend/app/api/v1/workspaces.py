from __future__ import annotations
import logging
import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.models.user import User
from app.models.workspace_instance import WorkspaceInstance
from app.schemas.workspace_instance import (
    WorkspaceInstanceLogs,
    WorkspaceInstanceRead,
    WorkspaceMetrics,
)
from app.services.workspace.workspace_lifecycle import WorkspaceLifecycleService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _enqueue_launch(workspace_id: uuid.UUID) -> None:
    """Dispatch the launch worker; tolerate a missing broker (status stays pending).

    ``retry=False`` ensures a single, fail-fast publish attempt so the request
    never blocks when the broker is unreachable (e.g. local dev or tests).
    """
    try:
        from app.workers.tasks import launch_workspace_task

        launch_workspace_task.apply_async(args=[str(workspace_id)], retry=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("workspace_launch_enqueue_failed", extra={"workspace_id": str(workspace_id), "error": str(exc)[:200]})


@router.get("", response_model=list[WorkspaceInstanceRead])
def list_workspaces(
    repository_id: uuid.UUID = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[WorkspaceInstance]:
    return WorkspaceLifecycleService(db).list_for_repository(repository_id, current_user.organization_id)


@router.post("/{repository_id}/launch", response_model=WorkspaceInstanceRead, status_code=202)
def launch_workspace_instance(
    repository_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WorkspaceInstance:
    """Create a sandbox instance (pending) and enqueue the real launch lifecycle.

    Requires a Workspace Provision plan. The instance progresses asynchronously
    through provisioning -> installing -> starting -> running (or failed); poll
    GET /workspaces/{id} for status.
    """
    instance = WorkspaceLifecycleService(db).create(
        repository_id=repository_id,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
    )
    _enqueue_launch(instance.id)
    return instance


@router.get("/metrics", response_model=WorkspaceMetrics)
def workspace_metrics(
    repository_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Aggregate launch/install/startup durations, status counts, and failures."""
    return WorkspaceLifecycleService(db).metrics(current_user.organization_id, repository_id)


@router.get("/{workspace_id}", response_model=WorkspaceInstanceRead)
def get_workspace_instance(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceInstance:
    return WorkspaceLifecycleService(db).get(workspace_id, current_user.organization_id)


@router.get("/{workspace_id}/logs", response_model=WorkspaceInstanceLogs)
def get_workspace_instance_logs(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceInstance:
    return WorkspaceLifecycleService(db).get(workspace_id, current_user.organization_id)


@router.post("/{workspace_id}/stop", response_model=WorkspaceInstanceRead)
def stop_workspace_instance(
    workspace_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WorkspaceInstance:
    return WorkspaceLifecycleService(db).stop(workspace_id, current_user.organization_id, current_user.id)


@router.post("/{workspace_id}/restart", response_model=WorkspaceInstanceRead, status_code=202)
def restart_workspace_instance(
    workspace_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WorkspaceInstance:
    """Stop the sandbox and re-run a fresh lifecycle on the same instance."""
    instance = WorkspaceLifecycleService(db).restart(workspace_id, current_user.organization_id, current_user.id)
    _enqueue_launch(instance.id)
    return instance


@router.post("/{workspace_id}/cancel", response_model=WorkspaceInstanceRead)
def cancel_workspace_instance(
    workspace_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WorkspaceInstance:
    """Cancel a launch that is still pending/provisioning/installing/starting."""
    return WorkspaceLifecycleService(db).cancel(workspace_id, current_user.organization_id, current_user.id)


@router.delete("/{workspace_id}", status_code=204)
def delete_workspace_instance(
    workspace_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    WorkspaceLifecycleService(db).delete(workspace_id, current_user.organization_id, current_user.id)
    return Response(status_code=204)
