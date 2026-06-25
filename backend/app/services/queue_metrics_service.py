from __future__ import annotations

from typing import Any

from redis import Redis

from app.core.config import settings
from app.services.dead_letter_service import DEAD_LETTER_SCANS_KEY


class QueueMetricsService:
    def __init__(self, redis_client: Redis | None = None, *, queue_name: str = "celery") -> None:
        self.redis = redis_client or Redis.from_url(settings.redis_url, decode_responses=True)
        self.queue_name = queue_name

    def get_metrics(self) -> dict[str, Any]:
        try:
            redis_connected = bool(self.redis.ping())
            pending_scan_task_count = int(self.redis.llen(self.queue_name))
            dead_letter_count = int(self.redis.llen(DEAD_LETTER_SCANS_KEY))
        except Exception:
            redis_connected = False
            pending_scan_task_count = 0
            dead_letter_count = 0

        return {
            "pending_scan_task_count": pending_scan_task_count,
            "dead_letter_count": dead_letter_count,
            "redis_connected": redis_connected,
            "queue_name": self.queue_name,
        }
