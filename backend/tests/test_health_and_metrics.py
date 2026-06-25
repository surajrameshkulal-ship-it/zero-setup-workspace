from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.api.v1.admin import get_queue_metrics_service
from app.api.v1.health import get_health_check_service
from app.models.user import UserRole
from app.services.health_service import HealthCheckService
from app.services.queue_metrics_service import QueueMetricsService


class FakeRedis:
    def __init__(self, *, ping_ok: bool = True, lengths: dict[str, int] | None = None) -> None:
        self.ping_ok = ping_ok
        self.lengths = lengths or {}

    def ping(self) -> bool:
        return self.ping_ok

    def llen(self, key: str) -> int:
        return self.lengths.get(key, 0)


class FakeHealthService:
    def check(self) -> dict:
        return {
            "status": "ok",
            "app_status": "ok",
            "database_status": "ok",
            "redis_status": "ok",
            "celery_queue_reachable": True,
            "timestamp": datetime(2026, 6, 25, 10, 0, tzinfo=timezone.utc),
        }


class FakeQueueMetricsService:
    def get_metrics(self) -> dict:
        return {
            "pending_scan_task_count": 7,
            "dead_letter_count": 2,
            "redis_connected": True,
            "queue_name": "celery",
        }


def test_health_service_reports_dependencies(api_context) -> None:
    service = HealthCheckService(api_context.db, redis_client=FakeRedis(lengths={"celery": 3}))

    payload = service.check()

    assert payload["status"] == "ok"
    assert payload["database_status"] == "ok"
    assert payload["redis_status"] == "ok"
    assert payload["celery_queue_reachable"] is True


def test_root_and_api_health_endpoints(api_context) -> None:
    api_context.client.app.dependency_overrides[get_health_check_service] = lambda: FakeHealthService()

    root_response = api_context.client.get("/health")
    api_response = api_context.client.get("/api/v1/health")

    assert root_response.status_code == 200
    assert api_response.status_code == 200
    assert root_response.json()["status"] == "ok"
    assert api_response.json()["database_status"] == "ok"


def test_queue_metrics_service_reads_redis_counts() -> None:
    service = QueueMetricsService(
        redis_client=FakeRedis(lengths={"celery": 4, "codedna:dead_letter_scans": 2}),
        queue_name="celery",
    )

    assert service.get_metrics() == {
        "pending_scan_task_count": 4,
        "dead_letter_count": 2,
        "redis_connected": True,
        "queue_name": "celery",
    }


def test_admin_queue_metrics_endpoint_requires_admin_and_returns_metrics(api_context) -> None:
    api_context.client.app.dependency_overrides[get_queue_metrics_service] = lambda: FakeQueueMetricsService()

    response = api_context.client.get("/api/v1/admin/queue-metrics")

    assert response.status_code == 200
    assert response.json() == {
        "pending_scan_task_count": 7,
        "dead_letter_count": 2,
        "redis_connected": True,
        "queue_name": "celery",
    }


def test_admin_endpoint_rejects_non_admin(api_context) -> None:
    from app.api.deps import get_current_user

    member = SimpleNamespace(
        id=api_context.user.id,
        organization_id=api_context.user.organization_id,
        role=UserRole.MEMBER,
    )
    api_context.client.app.dependency_overrides[get_current_user] = lambda: member

    response = api_context.client.get("/api/v1/admin/queue-metrics")

    assert response.status_code == 403
