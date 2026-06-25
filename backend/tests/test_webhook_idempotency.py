from __future__ import annotations

import logging

from sqlalchemy import select

from app.models.github import GitHubInstallation
from app.models.scan import PullRequestScan
from app.services.webhook_service import GitHubWebhookService
from app.workers import tasks


def _install_github_app(api_context, installation_id: int = 424242) -> GitHubInstallation:
    installation = GitHubInstallation(
        organization_id=api_context.organization.id,
        installation_id=installation_id,
        account_login="acme",
        account_type="Organization",
        permissions={"pull_requests": "read", "checks": "write", "contents": "read"},
    )
    api_context.db.add(installation)
    api_context.db.commit()
    return installation


def _pull_request_payload(
    *,
    installation_id: int,
    action: str = "opened",
    repository_id: int = 1001,
    pr_number: int = 101,
    head_sha: str = "1" * 40,
) -> dict:
    return {
        "action": action,
        "installation": {"id": installation_id},
        "repository": {
            "id": repository_id,
            "owner": {"login": "acme"},
            "name": "payments-api",
            "full_name": "acme/payments-api",
            "default_branch": "main",
        },
        "pull_request": {
            "number": pr_number,
            "html_url": f"https://github.com/acme/payments-api/pull/{pr_number}",
            "title": "Test PR",
            "head": {"sha": head_sha},
            "base": {"sha": "b" * 40},
        },
        "sender": {"login": "octocat"},
    }


def _webhook_scans(api_context, *, pr_number: int) -> list[PullRequestScan]:
    return list(
        api_context.db.scalars(
            select(PullRequestScan)
            .where(
                PullRequestScan.repository_id == api_context.repository.id,
                PullRequestScan.github_pr_number == pr_number,
                PullRequestScan.trigger == "webhook",
            )
            .order_by(PullRequestScan.created_at.asc())
        )
    )


def _capture_enqueued_scans(monkeypatch) -> list[str]:
    enqueued_scan_ids: list[str] = []

    def fake_delay(scan_id: str) -> None:
        enqueued_scan_ids.append(scan_id)

    monkeypatch.setattr(tasks.run_pr_scan, "delay", fake_delay)
    return enqueued_scan_ids


def test_same_webhook_delivered_twice_creates_only_one_scan(api_context, monkeypatch, caplog) -> None:
    installation = _install_github_app(api_context)
    enqueued_scan_ids = _capture_enqueued_scans(monkeypatch)
    service = GitHubWebhookService(api_context.db)
    payload = _pull_request_payload(installation_id=installation.installation_id)

    with caplog.at_level(logging.INFO):
        first_response = service.handle(event="pull_request", payload=payload)
        second_response = service.handle(event="pull_request", payload=payload)

    scans = _webhook_scans(api_context, pr_number=101)
    assert len(scans) == 1
    assert scans[0].idempotency_key
    assert first_response.scan_id == scans[0].id
    assert second_response.scan_id == scans[0].id
    assert enqueued_scan_ids == [str(scans[0].id)]
    assert "webhook_idempotency_key_generated" in caplog.messages
    assert "duplicate_scan_detected" in caplog.messages
    assert "duplicate_scan_skipped" in caplog.messages
    assert "scan_created_from_webhook" in caplog.messages


def test_same_pr_with_same_head_sha_creates_only_one_scan(api_context, monkeypatch) -> None:
    installation = _install_github_app(api_context)
    enqueued_scan_ids = _capture_enqueued_scans(monkeypatch)
    service = GitHubWebhookService(api_context.db)

    service.handle(
        event="pull_request",
        payload=_pull_request_payload(
            installation_id=installation.installation_id,
            action="opened",
            pr_number=102,
            head_sha="2" * 40,
        ),
    )
    duplicate_response = service.handle(
        event="pull_request",
        payload=_pull_request_payload(
            installation_id=installation.installation_id,
            action="synchronize",
            pr_number=102,
            head_sha="2" * 40,
        ),
    )

    scans = _webhook_scans(api_context, pr_number=102)
    assert len(scans) == 1
    assert duplicate_response.scan_id == scans[0].id
    assert enqueued_scan_ids == [str(scans[0].id)]


def test_same_pr_with_new_head_sha_creates_new_scan(api_context, monkeypatch) -> None:
    installation = _install_github_app(api_context)
    enqueued_scan_ids = _capture_enqueued_scans(monkeypatch)
    service = GitHubWebhookService(api_context.db)

    service.handle(
        event="pull_request",
        payload=_pull_request_payload(
            installation_id=installation.installation_id,
            action="opened",
            pr_number=103,
            head_sha="3" * 40,
        ),
    )
    service.handle(
        event="pull_request",
        payload=_pull_request_payload(
            installation_id=installation.installation_id,
            action="synchronize",
            pr_number=103,
            head_sha="4" * 40,
        ),
    )

    scans = _webhook_scans(api_context, pr_number=103)
    assert len(scans) == 2
    assert {scan.head_sha for scan in scans} == {"3" * 40, "4" * 40}
    assert all(scan.idempotency_key for scan in scans)
    assert len({scan.idempotency_key for scan in scans}) == 2
    assert enqueued_scan_ids == [str(scan.id) for scan in scans]


def test_duplicate_webhook_does_not_enqueue_celery_twice(api_context, monkeypatch) -> None:
    installation = _install_github_app(api_context)
    enqueued_scan_ids = _capture_enqueued_scans(monkeypatch)
    service = GitHubWebhookService(api_context.db)
    payload = _pull_request_payload(
        installation_id=installation.installation_id,
        pr_number=104,
        head_sha="5" * 40,
    )

    for _ in range(3):
        response = service.handle(event="pull_request", payload=payload)
        assert response.accepted is True

    scans = _webhook_scans(api_context, pr_number=104)
    assert len(scans) == 1
    assert enqueued_scan_ids == [str(scans[0].id)]
