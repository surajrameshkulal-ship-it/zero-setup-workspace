from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from redis import Redis

from app.core.config import settings
from app.services.types import ChangedFile

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AIReviewLimitResult:
    allowed: bool
    reason: str | None = None


class AIReviewLimitService:
    def __init__(self, redis_client: Redis | None = None) -> None:
        self.redis = redis_client or Redis.from_url(settings.redis_url, decode_responses=True)

    def check_and_record(self, files: list[ChangedFile]) -> AIReviewLimitResult:
        diff_chars = sum(len(file.patch or "") for file in files)
        logger.info(
            "ai_limit_check_started",
            extra={
                "file_count": len(files),
                "diff_chars": diff_chars,
                "daily_limit": settings.ai_daily_request_limit,
                "monthly_limit": settings.ai_monthly_request_limit,
                "max_files": settings.ai_max_files_per_review,
                "max_diff_chars": settings.ai_max_diff_chars,
            },
        )

        if settings.ai_max_files_per_review > 0 and len(files) > settings.ai_max_files_per_review:
            return self._exceeded(
                f"changed file count {len(files)} exceeds limit {settings.ai_max_files_per_review}",
                "max_files",
            )

        if settings.ai_max_diff_chars > 0 and diff_chars > settings.ai_max_diff_chars:
            return self._exceeded(
                f"diff size {diff_chars} characters exceeds limit {settings.ai_max_diff_chars}",
                "max_diff_chars",
            )

        if settings.ai_daily_request_limit <= 0 and settings.ai_monthly_request_limit <= 0:
            return AIReviewLimitResult(allowed=True)

        try:
            now = datetime.now(timezone.utc)
            daily_key = f"codedna:ai_review_requests:daily:{now:%Y%m%d}"
            monthly_key = f"codedna:ai_review_requests:monthly:{now:%Y%m}"
            daily_count = int(self.redis.get(daily_key) or 0)
            monthly_count = int(self.redis.get(monthly_key) or 0)

            if settings.ai_daily_request_limit > 0 and daily_count >= settings.ai_daily_request_limit:
                return self._exceeded(
                    f"daily AI review request limit {settings.ai_daily_request_limit} reached",
                    "daily_request_limit",
                )
            if settings.ai_monthly_request_limit > 0 and monthly_count >= settings.ai_monthly_request_limit:
                return self._exceeded(
                    f"monthly AI review request limit {settings.ai_monthly_request_limit} reached",
                    "monthly_request_limit",
                )

            self.redis.incr(daily_key)
            self.redis.expire(daily_key, 60 * 60 * 48)
            self.redis.incr(monthly_key)
            self.redis.expire(monthly_key, 60 * 60 * 24 * 40)
        except Exception as exc:
            logger.warning(
                "ai_limit_check_unavailable",
                extra={"error": str(exc)[:500]},
            )
            return AIReviewLimitResult(allowed=True)

        return AIReviewLimitResult(allowed=True)

    def _exceeded(self, reason: str, limit_type: str) -> AIReviewLimitResult:
        logger.warning(
            "ai_limit_exceeded",
            extra={"limit_type": limit_type, "reason": reason},
        )
        return AIReviewLimitResult(allowed=False, reason=reason)
