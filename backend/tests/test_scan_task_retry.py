from __future__ import annotations

import logging
import uuid
from types import SimpleNamespace

import pytest

from app.workers.tasks import MAX_SCAN_RETRIES, _run_pr_scan_with_retry


class TransientScanError(RuntimeError):
    pass


class RetryScheduled(Exception):
    pass


class FakeTask:
    def __init__(self, *, retries: int = 0, max_retries: int = MAX_SCAN_RETRIES) -> None:
        self.request = SimpleNamespace(retries=retries)
        self.max_retries = max_retries
        self.retry_calls: list[dict] = []

    def retry(self, **kwargs):
        self.retry_calls.append(kwargs)
        raise RetryScheduled


class FakeSession:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeScanService:
    def __init__(self, db: FakeSession, *, error: Exception | None = None) -> None:
        self.db = db
        self.error = error
        self.failed_scan = SimpleNamespace(
            id=uuid.uuid4(),
            repository_id=uuid.uuid4(),
            github_pr_number=42,
            head_sha="a" * 40,
        )
        self.run_calls: list[dict] = []
        self.mark_failed_calls: list[dict] = []

    def run(self, scan_id: uuid.UUID, *, mark_failed_on_error: bool = True) -> None:
        self.run_calls.append({"scan_id": scan_id, "mark_failed_on_error": mark_failed_on_error})
        if self.error:
            raise self.error

    def mark_failed(self, scan_id: uuid.UUID, failure_reason: str) -> None:
        self.mark_failed_calls.append({"scan_id": scan_id, "failure_reason": failure_reason})
        self.failed_scan.id = scan_id
        return self.failed_scan


class FakeDeadLetterService:
    def __init__(self) -> None:
        self.enqueue_calls: list[dict] = []

    def enqueue(self, **kwargs) -> dict:
        self.enqueue_calls.append(kwargs)
        return kwargs


def test_scan_task_retries_transient_error_with_backoff(caplog) -> None:
    scan_id = str(uuid.uuid4())
    task = FakeTask(retries=1)
    session = FakeSession()
    service = FakeScanService(session, error=TransientScanError("temporary github outage"))
    dead_letters = FakeDeadLetterService()

    with caplog.at_level(logging.INFO):
        with pytest.raises(RetryScheduled):
            _run_pr_scan_with_retry(
                task=task,
                scan_id=scan_id,
                session_factory=lambda: session,
                service_factory=lambda db: service,
                dead_letter_service_factory=lambda: dead_letters,
            )

    assert service.run_calls == [
        {"scan_id": uuid.UUID(scan_id), "mark_failed_on_error": False},
    ]
    assert service.mark_failed_calls == []
    assert dead_letters.enqueue_calls == []
    assert task.retry_calls == [
        {
            "exc": service.error,
            "countdown": 2,
            "max_retries": MAX_SCAN_RETRIES,
        }
    ]
    assert session.closed is True
    assert "scan_retry_attempt" in caplog.messages
    assert "scan_retry_scheduled" in caplog.messages


def test_scan_task_respects_max_retries_and_stops_retrying(caplog) -> None:
    scan_id = str(uuid.uuid4())
    task = FakeTask(retries=MAX_SCAN_RETRIES)
    session = FakeSession()
    service = FakeScanService(session, error=TransientScanError("semgrep unavailable"))
    dead_letters = FakeDeadLetterService()

    with caplog.at_level(logging.INFO):
        with pytest.raises(TransientScanError):
            _run_pr_scan_with_retry(
                task=task,
                scan_id=scan_id,
                session_factory=lambda: session,
                service_factory=lambda db: service,
                dead_letter_service_factory=lambda: dead_letters,
            )

    assert task.retry_calls == []
    assert service.mark_failed_calls == [
        {"scan_id": uuid.UUID(scan_id), "failure_reason": "semgrep unavailable"},
    ]
    assert dead_letters.enqueue_calls == [
        {
            "scan": service.failed_scan,
            "error_message": "semgrep unavailable",
            "retry_count": MAX_SCAN_RETRIES,
        }
    ]
    assert session.closed is True
    assert "scan_retry_exhausted" in caplog.messages


def test_scan_task_marks_scan_failed_after_retries_exhausted() -> None:
    scan_id = str(uuid.uuid4())
    task = FakeTask(retries=MAX_SCAN_RETRIES)
    session = FakeSession()
    service = FakeScanService(session, error=TransientScanError("database timeout"))
    dead_letters = FakeDeadLetterService()

    with pytest.raises(TransientScanError):
        _run_pr_scan_with_retry(
            task=task,
            scan_id=scan_id,
            session_factory=lambda: session,
            service_factory=lambda db: service,
            dead_letter_service_factory=lambda: dead_letters,
        )

    assert service.mark_failed_calls == [
        {"scan_id": uuid.UUID(scan_id), "failure_reason": "database timeout"},
    ]
