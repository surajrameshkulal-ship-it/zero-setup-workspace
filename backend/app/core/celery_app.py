from __future__ import annotations
from celery import Celery

from app.core.config import settings


celery_app = Celery(
    "codedna_ai",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    timezone="UTC",
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        # Heartbeat/liveness sweep for running sandboxes (crashed detection).
        "workspace-reconcile": {
            "task": "workspace.reconcile_workspaces_task",
            "schedule": 30.0,
        },
        # Purge terminal sandbox instances older than the configured TTL.
        "workspace-cleanup": {
            "task": "workspace.cleanup_workspaces_task",
            "schedule": 3600.0,
        },
    },
)
