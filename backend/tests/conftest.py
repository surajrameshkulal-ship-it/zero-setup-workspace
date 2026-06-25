from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-codedna-ai")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("GITHUB_WEBHOOK_SECRET", "test-webhook-secret")

from app.api.deps import get_current_user  # noqa: E402
from app.core.database import get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Base  # noqa: E402
from app.models.organization import Organization  # noqa: E402
from app.models.repository import Repository  # noqa: E402
from app.models.scan import PullRequestScan, RiskLevel, ScanStatus  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402


@pytest.fixture
def api_context():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    now = datetime.now(timezone.utc)

    organization = Organization(name="Acme Engineering", slug="acme")
    other_organization = Organization(name="Other Co", slug="other")
    db.add_all([organization, other_organization])
    db.flush()

    current_user = User(
        organization_id=organization.id,
        email="admin@acme.test",
        full_name="Acme Admin",
        hashed_password="not-used",
        role=UserRole.ADMIN,
    )
    other_user = User(
        organization_id=other_organization.id,
        email="admin@other.test",
        full_name="Other Admin",
        hashed_password="not-used",
        role=UserRole.ADMIN,
    )
    repository = Repository(
        organization_id=organization.id,
        github_repository_id=1001,
        owner="acme",
        name="payments-api",
        full_name="acme/payments-api",
        default_branch="main",
    )
    other_repository = Repository(
        organization_id=other_organization.id,
        github_repository_id=2001,
        owner="other",
        name="private-api",
        full_name="other/private-api",
        default_branch="main",
    )
    db.add_all([current_user, other_user, repository, other_repository])
    db.flush()

    completed_scan = PullRequestScan(
        organization_id=organization.id,
        repository_id=repository.id,
        github_pr_number=12,
        github_pr_url="https://github.com/acme/payments-api/pull/12",
        title="Remove debug logging",
        head_sha="a" * 40,
        base_sha="b" * 40,
        github_check_run_id=12345,
        status=ScanStatus.COMPLETED,
        trigger="webhook",
        files_changed=2,
        lines_added=20,
        lines_deleted=5,
        risk_score=72.5,
        risk_level=RiskLevel.HIGH,
        summary="Company rule violation found.",
        semgrep_findings=[],
        ai_findings=[],
        company_rule_violations=[{"title": "No console.log", "severity": "medium"}],
        architecture_violations=[{"title": "No UI to DB import", "severity": "high"}],
        report={
            "risk": {"score": 72.5, "level": "high"},
            "ai_review": {
                "summary": "Review found logging concerns.",
                "security_issues": ["Avoid logging secrets."],
                "bug_risks": [],
                "performance_concerns": [],
                "maintainability_suggestions": [],
                "recommended_action": "Remove debug logging.",
            },
            "ai_review_markdown": "### Summary\n- Review found logging concerns.",
        },
        created_at=now - timedelta(minutes=5),
        updated_at=now - timedelta(minutes=4),
        completed_at=now - timedelta(minutes=4),
    )
    failed_scan = PullRequestScan(
        organization_id=organization.id,
        repository_id=repository.id,
        github_pr_number=13,
        title="Broken scan",
        head_sha="c" * 40,
        base_sha="d" * 40,
        status=ScanStatus.FAILED,
        trigger="webhook",
        risk_score=None,
        risk_level=None,
        failure_reason="GitHub API timeout",
        semgrep_findings=[],
        ai_findings=[],
        company_rule_violations=[],
        architecture_violations=[],
        report={},
        created_at=now - timedelta(minutes=1),
        updated_at=now - timedelta(minutes=1),
        completed_at=now - timedelta(minutes=1),
    )
    other_scan = PullRequestScan(
        organization_id=other_organization.id,
        repository_id=other_repository.id,
        github_pr_number=99,
        title="Other org PR",
        head_sha="e" * 40,
        base_sha="f" * 40,
        status=ScanStatus.COMPLETED,
        trigger="webhook",
        risk_score=100,
        risk_level=RiskLevel.CRITICAL,
        semgrep_findings=[{"title": "Secret leak"}],
        ai_findings=[],
        company_rule_violations=[],
        architecture_violations=[],
        report={},
        created_at=now,
        updated_at=now,
        completed_at=now,
    )
    db.add_all([completed_scan, failed_scan, other_scan])
    db.commit()

    app = create_app()

    def override_get_db():
        yield db

    def override_get_current_user():
        return current_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client,
            db=db,
            user=current_user,
            organization=organization,
            repository=repository,
            completed_scan=completed_scan,
            failed_scan=failed_scan,
            other_organization=other_organization,
            other_repository=other_repository,
            other_scan=other_scan,
        )

    app.dependency_overrides.clear()
    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
