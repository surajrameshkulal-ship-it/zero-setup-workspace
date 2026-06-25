from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.api.v1.admin import get_dead_letter_scan_service
from app.services.dead_letter_service import DEAD_LETTER_SCANS_KEY, DeadLetterScanService


class FakeRedis:
    def __init__(self) -> None:
        self.items: list[str] = []
        self.lpush_calls: list[tuple[str, str]] = []

    def lpush(self, key: str, value: str) -> int:
        self.lpush_calls.append((key, value))
        self.items.insert(0, value)
        return len(self.items)

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        if key != DEAD_LETTER_SCANS_KEY:
            return []
        return self.items[start : end + 1]


def _scan() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        repository_id=uuid.uuid4(),
        github_pr_number=17,
        head_sha="f" * 40,
    )


def test_failed_scan_is_added_to_dead_letter_queue(caplog) -> None:
    redis = FakeRedis()
    service = DeadLetterScanService(redis_client=redis)
    scan = _scan()
    failed_at = datetime(2026, 6, 24, 12, 30, tzinfo=timezone.utc)

    with caplog.at_level(logging.INFO):
        payload = service.enqueue(
            scan=scan,
            error_message="GitHub timeout",
            retry_count=3,
            failed_at=failed_at,
        )

    assert redis.lpush_calls
    key, raw_payload = redis.lpush_calls[0]
    assert key == DEAD_LETTER_SCANS_KEY
    assert json.loads(raw_payload) == payload
    assert "dead_letter_enqueue_started" in caplog.messages
    assert "dead_letter_enqueue_completed" in caplog.messages


def test_dead_letter_payload_contains_required_fields() -> None:
    redis = FakeRedis()
    service = DeadLetterScanService(redis_client=redis)
    scan = _scan()

    payload = service.enqueue(scan=scan, error_message="Semgrep unavailable", retry_count=3)

    assert set(payload) == {
        "scan_id",
        "repository_id",
        "pull_request_number",
        "head_sha",
        "error_message",
        "failed_at",
        "retry_count",
    }
    assert payload["scan_id"] == str(scan.id)
    assert payload["repository_id"] == str(scan.repository_id)
    assert payload["pull_request_number"] == 17
    assert payload["head_sha"] == "f" * 40
    assert payload["error_message"] == "Semgrep unavailable"
    assert payload["retry_count"] == 3


def test_admin_api_returns_dead_letter_scan_items(api_context) -> None:
    class FakeDeadLetterService:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def list_recent(self, *, limit: int, repository_ids: set[uuid.UUID]) -> list[dict]:
            self.calls.append({"limit": limit, "repository_ids": repository_ids})
            allowed = {str(repository_id) for repository_id in repository_ids}
            return [
                item
                for item in [
                    {
                        "scan_id": str(uuid.uuid4()),
                        "repository_id": str(api_context.repository.id),
                        "pull_request_number": 17,
                        "head_sha": "f" * 40,
                        "error_message": "GitHub timeout",
                        "failed_at": "2026-06-24T12:30:00+00:00",
                        "retry_count": 3,
                    },
                    {
                        "scan_id": str(uuid.uuid4()),
                        "repository_id": str(api_context.other_repository.id),
                        "pull_request_number": 99,
                        "head_sha": "e" * 40,
                        "error_message": "Other org failure",
                        "failed_at": "2026-06-24T12:31:00+00:00",
                        "retry_count": 3,
                    },
                ]
                if item["repository_id"] in allowed
            ][:limit]

    fake_service = FakeDeadLetterService()
    api_context.client.app.dependency_overrides[get_dead_letter_scan_service] = lambda: fake_service

    response = api_context.client.get("/api/v1/admin/dead-letter-scans", params={"limit": 10})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["repository_id"] == str(api_context.repository.id)
    assert payload[0]["pull_request_number"] == 17
    assert payload[0]["error_message"] == "GitHub timeout"
    assert fake_service.calls == [
        {
            "limit": 10,
            "repository_ids": {api_context.repository.id},
        }
    ]
