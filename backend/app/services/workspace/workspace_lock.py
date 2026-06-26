"""Per-repository workspace launch lock (Phase 11.1 hardening).

Ensures only one launch can be created for a repository at a time. Uses Redis
(SET NX EX) when a broker URL is configured and reachable; otherwise it is a
no-op and the application-level concurrency guard in the lifecycle service (an
"active instance already exists" check) provides single-launch semantics.
"""

from __future__ import annotations

import logging
import uuid

from app.core.config import settings

logger = logging.getLogger(__name__)

LOCK_TTL_SECONDS = 120


class WorkspaceLock:
    def __init__(self, *, redis_client=None, ttl: int = LOCK_TTL_SECONDS) -> None:
        self.ttl = ttl
        self._client = redis_client
        self._token: str | None = None
        if self._client is None:
            self._client = self._build_client()

    @staticmethod
    def _build_client():
        try:
            import redis  # type: ignore

            client = redis.Redis.from_url(
                settings.redis_url, socket_connect_timeout=0.5, socket_timeout=0.5
            )
            client.ping()
            return client
        except Exception:  # noqa: BLE001 - redis is optional; fall back to the DB guard
            return None

    def _key(self, repository_id: uuid.UUID) -> str:
        return f"codedna:workspace-lock:{repository_id}"

    def acquire(self, repository_id: uuid.UUID) -> bool:
        if self._client is None:
            return True  # no distributed lock available; rely on the DB guard
        try:
            self._token = uuid.uuid4().hex
            return bool(self._client.set(self._key(repository_id), self._token, nx=True, ex=self.ttl))
        except Exception:  # noqa: BLE001
            return True

    def release(self, repository_id: uuid.UUID) -> None:
        if self._client is None or self._token is None:
            return
        try:
            # Best-effort release (only if we still own the token).
            if self._client.get(self._key(repository_id)) == self._token.encode():
                self._client.delete(self._key(repository_id))
        except Exception:  # noqa: BLE001
            pass
