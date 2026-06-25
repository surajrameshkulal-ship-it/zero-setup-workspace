from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from redis import Redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings

logger = logging.getLogger(__name__)


class HealthCheckService:
    def __init__(self, db: Session, redis_client: Redis | None = None, *, queue_name: str = "celery") -> None:
        self.db = db
        self.redis = redis_client or Redis.from_url(settings.redis_url, decode_responses=True)
        self.queue_name = queue_name

    def check(self) -> dict[str, Any]:
        logger.info("health_check_started")
        database_status = self._database_status()
        redis_status = self._redis_status()
        celery_queue_reachable = self._celery_queue_reachable() if redis_status == "ok" else False
        status = "ok" if database_status == "ok" and redis_status == "ok" and celery_queue_reachable else "degraded"
        payload = {
            "status": status,
            "app_status": "ok",
            "database_status": database_status,
            "redis_status": redis_status,
            "celery_queue_reachable": celery_queue_reachable,
            "timestamp": datetime.now(timezone.utc),
        }
        if status != "ok":
            logger.warning(
                "health_check_failed",
                extra={
                    "database_status": database_status,
                    "redis_status": redis_status,
                    "celery_queue_reachable": celery_queue_reachable,
                },
            )
        logger.info(
            "health_check_completed",
            extra={
                "status": status,
                "database_status": database_status,
                "redis_status": redis_status,
                "celery_queue_reachable": celery_queue_reachable,
            },
        )
        return payload

    def _database_status(self) -> str:
        try:
            self.db.execute(text("SELECT 1"))
        except Exception:
            return "error"
        return "ok"

    def _redis_status(self) -> str:
        try:
            return "ok" if self.redis.ping() else "error"
        except Exception:
            return "error"

    def _celery_queue_reachable(self) -> bool:
        try:
            self.redis.llen(self.queue_name)
        except Exception:
            return False
        return True
