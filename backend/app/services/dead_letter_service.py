from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from redis import Redis

from app.core.config import settings
from app.models.scan import PullRequestScan

logger = logging.getLogger(__name__)

DEAD_LETTER_SCANS_KEY = "codedna:dead_letter_scans"


class DeadLetterScanService:
    def __init__(self, redis_client: Redis | None = None) -> None:
        self.redis = redis_client or Redis.from_url(settings.redis_url, decode_responses=True)

    def enqueue(
        self,
        *,
        scan: PullRequestScan,
        error_message: str,
        retry_count: int,
        failed_at: datetime | None = None,
    ) -> dict[str, Any]:
        failed_at = failed_at or datetime.now(timezone.utc)
        payload = {
            "scan_id": str(scan.id),
            "repository_id": str(scan.repository_id),
            "pull_request_number": scan.github_pr_number,
            "head_sha": scan.head_sha,
            "error_message": error_message,
            "failed_at": failed_at.isoformat(),
            "retry_count": retry_count,
        }

        logger.info(
            "dead_letter_enqueue_started",
            extra={
                "scan_id": payload["scan_id"],
                "repository_id": payload["repository_id"],
                "pr_number": payload["pull_request_number"],
                "retry_count": retry_count,
            },
        )
        try:
            self.redis.lpush(DEAD_LETTER_SCANS_KEY, json.dumps(payload, sort_keys=True, separators=(",", ":")))
        except Exception as exc:
            logger.exception(
                "dead_letter_enqueue_failed",
                extra={
                    "scan_id": payload["scan_id"],
                    "repository_id": payload["repository_id"],
                    "pr_number": payload["pull_request_number"],
                    "retry_count": retry_count,
                    "error": str(exc)[:500],
                },
            )
            raise

        logger.info(
            "dead_letter_enqueue_completed",
            extra={
                "scan_id": payload["scan_id"],
                "repository_id": payload["repository_id"],
                "pr_number": payload["pull_request_number"],
                "retry_count": retry_count,
            },
        )
        return payload

    def list_recent(
        self,
        *,
        limit: int = 50,
        repository_ids: Iterable[uuid.UUID | str] | None = None,
    ) -> list[dict[str, Any]]:
        allowed_repository_ids = {str(repository_id) for repository_id in repository_ids} if repository_ids is not None else None
        raw_items = self.redis.lrange(DEAD_LETTER_SCANS_KEY, 0, limit - 1)
        items: list[dict[str, Any]] = []
        for raw_item in raw_items:
            if isinstance(raw_item, bytes):
                raw_item = raw_item.decode("utf-8")
            try:
                payload = json.loads(raw_item)
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            repository_id = payload.get("repository_id")
            if allowed_repository_ids is not None and repository_id not in allowed_repository_ids:
                continue
            items.append(payload)
        return items
