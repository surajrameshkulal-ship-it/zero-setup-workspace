from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.core.errors import IntegrationError
from app.models.github import GitHubInstallation
from app.models.scan import PullRequestScan, ScanStatus
from app.services.check_run_report import CHECK_RUN_NAME, CheckRunReportBuilder
from app.services.scan_service import PullRequestScanService


class FakeDB:
    def __init__(self) -> None:
        self.commit_count = 0
        self.refreshed = []

    def commit(self) -> None:
        self.commit_count += 1

    def refresh(self, obj: object) -> None:
        self.refreshed.append(obj)


class FakeGitHub:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.created_payloads = []
        self.updated_payloads = []

    def create_check_run(self, **kwargs):
        self.created_payloads.append(kwargs)
        return self.response

    def update_check_run(self, **kwargs):
        self.updated_payloads.append(kwargs)
        return {}


def build_service(fake_db: FakeDB, fake_github: FakeGitHub) -> PullRequestScanService:
    service = PullRequestScanService.__new__(PullRequestScanService)
    service.db = fake_db
    service.github = fake_github
    service.check_run_report = CheckRunReportBuilder()
    return service


def build_scan():
    repository = SimpleNamespace(
        owner="surajrameshkulal-ship-it",
        name="single-page-cv",
        full_name="surajrameshkulal-ship-it/single-page-cv",
        github_installation=SimpleNamespace(installation_id=142102916),
    )
    return SimpleNamespace(
        id=uuid.uuid4(),
        repository=repository,
        github_pr_number=1,
        head_sha="abc3ace0a4581111111111111111111111111111",
        base_sha="e40cc5e110cf2222222222222222222222222222",
        github_check_run_id=None,
    )


def test_check_run_creation_uses_head_sha_and_commits_returned_id() -> None:
    fake_db = FakeDB()
    fake_github = FakeGitHub({"id": 9876543210})
    service = build_service(fake_db, fake_github)
    scan = build_scan()

    service._mark_check_run_in_progress(scan)

    assert scan.github_check_run_id == 9876543210
    assert fake_db.commit_count == 1
    assert fake_db.refreshed == [scan]
    assert fake_github.created_payloads == [
        {
            "installation_id": 142102916,
            "owner": "surajrameshkulal-ship-it",
            "repo": "single-page-cv",
            "name": CHECK_RUN_NAME,
            "head_sha": scan.head_sha,
            "status": "in_progress",
            "output": {
                "title": "CodeDNA AI Scan Report",
                "summary": "CodeDNA AI scan is in progress for PR #1 at `abc3ace0a458`.",
            },
        }
    ]


def test_check_run_creation_missing_id_raises_without_committing() -> None:
    fake_db = FakeDB()
    fake_github = FakeGitHub({"message": "created but malformed"})
    service = build_service(fake_db, fake_github)
    scan = build_scan()

    with pytest.raises(IntegrationError):
        service._mark_check_run_in_progress(scan)

    assert scan.github_check_run_id is None
    assert fake_db.commit_count == 0


def test_mark_failed_updates_github_check_run_as_failure(api_context) -> None:
    installation = GitHubInstallation(
        organization_id=api_context.organization.id,
        installation_id=142102916,
        account_login="acme",
        account_type="Organization",
        permissions={"checks": "write"},
    )
    api_context.db.add(installation)
    api_context.db.flush()
    api_context.repository.github_installation_id = installation.id

    scan = PullRequestScan(
        organization_id=api_context.organization.id,
        repository_id=api_context.repository.id,
        github_pr_number=55,
        title="Retry failure",
        head_sha="a" * 40,
        base_sha="b" * 40,
        github_check_run_id=987654,
        status=ScanStatus.RUNNING,
        trigger="webhook",
        semgrep_findings=[],
        ai_findings=[],
        company_rule_violations=[],
        architecture_violations=[],
        report={},
    )
    api_context.db.add(scan)
    api_context.db.commit()

    fake_github = FakeGitHub({})
    service = PullRequestScanService(api_context.db, github=fake_github)

    service.mark_failed(scan.id, "Retries exhausted: GitHub timeout")

    api_context.db.refresh(scan)
    assert scan.status == ScanStatus.FAILED
    assert scan.failure_reason == "Retries exhausted: GitHub timeout"
    assert fake_github.updated_payloads == [
        {
            "installation_id": 142102916,
            "owner": "acme",
            "repo": "payments-api",
            "check_run_id": 987654,
            "status": "completed",
            "conclusion": "failure",
            "completed_at": fake_github.updated_payloads[0]["completed_at"],
            "output": {
                "title": "CodeDNA AI Scan Failed",
                "summary": (
                    "The scan failed before producing a complete report.\n\n"
                    "Error: Retries exhausted: GitHub timeout"
                ),
            },
        }
    ]
