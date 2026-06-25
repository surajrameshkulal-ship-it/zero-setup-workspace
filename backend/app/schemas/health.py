from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class HealthRead(BaseModel):
    status: str
    app_status: str
    database_status: str
    redis_status: str
    celery_queue_reachable: bool
    timestamp: datetime


class QueueMetricsRead(BaseModel):
    pending_scan_task_count: int
    dead_letter_count: int
    redis_connected: bool
    queue_name: str
