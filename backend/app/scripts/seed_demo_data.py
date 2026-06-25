"""Populate the database with realistic demo data for customer demonstrations.

This script is idempotent: it ensures a demo organization + admin user exist,
creates a fixed set of demo repositories, and (re)builds a deterministic set of
pull-request scans for each one so the dashboard, repository, and scan views all
look populated and lifelike.

Usage:
    python -m app.scripts.seed_demo_data
    python -m app.scripts.seed_demo_data --email demo@codedna.ai --password 'Demo@12345'
    python -m app.scripts.seed_demo_data --reset      # remove demo repos/scans first

Re-running is safe: existing demo scans are cleared and regenerated so you always
get the same known data set for a demo.
"""

from __future__ import annotations

import argparse
import os
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import SessionLocal
from app.models.organization import Organization
from app.models.repository import Repository
from app.models.scan import PullRequestScan, RiskLevel, ScanStatus
from app.services.auth_service import AuthService

DEFAULT_EMAIL = "demo@codedna.ai"
DEFAULT_PASSWORD = "Demo@12345"
DEFAULT_FULL_NAME = "CodeDNA Demo"
DEFAULT_ORG_NAME = "Acme Labs"
DEFAULT_ORG_SLUG = "acme-labs"

DEMO_OWNER = "acme-labs"
GITHUB_REPO_ID_BASE = 900_000_000
SEED = 20260625

# (name, default_branch, language hint used for finding paths)
REPOSITORIES: list[tuple[str, str, str]] = [
    ("payments-api", "main", "app/payments"),
    ("web-dashboard", "main", "src/components"),
    ("auth-service", "main", "internal/auth"),
    ("data-pipeline", "main", "pipeline/jobs"),
    ("mobile-app", "develop", "lib/screens"),
]


def _risk_level_for(score: float) -> RiskLevel:
    if score >= 75:
        return RiskLevel.CRITICAL
    if score >= 50:
        return RiskLevel.HIGH
    if score >= 25:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def _ai_review_markdown(title: str, risk: RiskLevel, highlights: list[str]) -> str:
    verdict = {
        RiskLevel.LOW: "Looks good. Low risk; safe to merge after a quick glance.",
        RiskLevel.MEDIUM: "Mergeable with minor follow-ups. A few items are worth addressing.",
        RiskLevel.HIGH: "Needs changes before merge. Several meaningful risks were found.",
        RiskLevel.CRITICAL: "Do not merge yet. Critical issues must be resolved first.",
    }[risk]
    bullets = "\n".join(f"- {item}" for item in highlights)
    return (
        f"## Summary\n"
        f"{verdict}\n\n"
        f"## What changed\n"
        f"This pull request — \"{title}\" — touches application logic and tests. "
        f"The diff was analyzed for security, correctness, and adherence to organization rules.\n\n"
        f"## Key findings\n"
        f"{bullets}\n\n"
        f"## Recommendation\n"
        f"Address the items above, re-run the checks, and request a human review for anything "
        f"flagged as high or critical severity."
    )


def _finding(severity: str, title: str, description: str, path: str, line: int, source: str, category: str) -> dict:
    return {
        "severity": severity,
        "title": title,
        "description": description,
        "path": path,
        "line": line,
        "source": source,
        "category": category,
    }


# Scan blueprints per repository: (pr_number, title, status, base_score, files, added, deleted, findings_spec)
# findings_spec keys: semgrep, ai, company, architecture -> count of findings to synthesize
SCAN_BLUEPRINTS: list[dict] = [
    {
        "title": "Add idempotency keys to webhook handler",
        "status": ScanStatus.COMPLETED,
        "score": 18.0,
        "files": 4, "added": 120, "deleted": 22,
        "findings": {"semgrep": 1, "ai": 1, "company": 0, "architecture": 0},
        "highlights": [
            "Webhook delivery IDs are now persisted, preventing duplicate scans.",
            "Consider adding a unit test for the replay-attack case.",
        ],
    },
    {
        "title": "Hard-coded API token in client",
        "status": ScanStatus.COMPLETED,
        "score": 82.0,
        "files": 2, "added": 38, "deleted": 4,
        "findings": {"semgrep": 2, "ai": 1, "company": 1, "architecture": 0},
        "highlights": [
            "A live-looking API token is committed in source — rotate and move to config.",
            "Input from the request body is used without validation.",
            "Violates company rule: secrets must come from the secret manager.",
        ],
    },
    {
        "title": "Refactor risk scoring service",
        "status": ScanStatus.COMPLETED,
        "score": 44.0,
        "files": 7, "added": 210, "deleted": 168,
        "findings": {"semgrep": 0, "ai": 2, "company": 0, "architecture": 1},
        "highlights": [
            "Scoring weights were extracted cleanly; good separation of concerns.",
            "One module now imports across a layer boundary — see architecture finding.",
        ],
    },
    {
        "title": "Bump dependencies and patch CVEs",
        "status": ScanStatus.COMPLETED,
        "score": 11.0,
        "files": 3, "added": 60, "deleted": 60,
        "findings": {"semgrep": 0, "ai": 1, "company": 0, "architecture": 0},
        "highlights": [
            "Dependency upgrades resolve two known advisories.",
            "No behavioral changes detected in the diff.",
        ],
    },
    {
        "title": "Introduce background export job",
        "status": ScanStatus.COMPLETED,
        "score": 63.0,
        "files": 9, "added": 340, "deleted": 41,
        "findings": {"semgrep": 1, "ai": 2, "company": 1, "architecture": 1},
        "highlights": [
            "Unbounded query could load the full table into memory.",
            "PII is written to logs at INFO level.",
            "Violates company rule: exports must be rate-limited.",
        ],
    },
    {
        "title": "Fix flaky auth integration test",
        "status": ScanStatus.RUNNING,
        "score": 0.0,
        "files": 1, "added": 14, "deleted": 9,
        "findings": {"semgrep": 0, "ai": 0, "company": 0, "architecture": 0},
        "highlights": [],
    },
    {
        "title": "Add pagination to scans endpoint",
        "status": ScanStatus.QUEUED,
        "score": 0.0,
        "files": 2, "added": 48, "deleted": 6,
        "findings": {"semgrep": 0, "ai": 0, "company": 0, "architecture": 0},
        "highlights": [],
    },
    {
        "title": "Migrate to async DB driver",
        "status": ScanStatus.FAILED,
        "score": 0.0,
        "files": 12, "added": 410, "deleted": 380,
        "findings": {"semgrep": 0, "ai": 0, "company": 0, "architecture": 0},
        "highlights": [],
    },
]

SEMGREP_TEMPLATES = [
    ("high", "Hard-coded secret detected", "A credential-like string is committed to source control.", "secrets"),
    ("medium", "Missing input validation", "User-controlled input reaches a sink without validation.", "security"),
    ("low", "Use of deprecated API", "This call is deprecated and scheduled for removal.", "maintainability"),
]
AI_TEMPLATES = [
    ("medium", "Potential N+1 query", "This loop issues a database query per iteration.", "performance"),
    ("low", "Unclear error handling", "The exception is swallowed without logging context.", "reliability"),
    ("high", "PII written to logs", "Personally identifiable information appears in a log statement.", "privacy"),
]
COMPANY_TEMPLATES = [
    ("high", "Secrets must use the secret manager", "Company policy CR-12 prohibits hard-coded secrets.", "policy"),
    ("medium", "Exports must be rate-limited", "Company policy CR-31 requires rate limits on bulk export.", "policy"),
]
ARCH_TEMPLATES = [
    ("medium", "Layer boundary crossed", "A service module imports directly from the web layer.", "architecture"),
]


def _build_findings(kind_counts: dict, path_root: str) -> dict[str, list[dict]]:
    rng = random.Random(f"{path_root}-{kind_counts}")

    def make(templates, count, src):
        out = []
        for i in range(count):
            sev, title, desc, cat = templates[i % len(templates)]
            line = rng.randint(12, 480)
            out.append(_finding(sev, title, desc, f"{path_root}/module_{i + 1}.py", line, src, cat))
        return out

    return {
        "semgrep_findings": make(SEMGREP_TEMPLATES, kind_counts["semgrep"], "semgrep"),
        "ai_findings": make(AI_TEMPLATES, kind_counts["ai"], "ai"),
        "company_rule_violations": make(COMPANY_TEMPLATES, kind_counts["company"], "company-rule"),
        "architecture_violations": make(ARCH_TEMPLATES, kind_counts["architecture"], "architecture"),
    }


def _ensure_repository(db, organization_id, owner: str, name: str, default_branch: str, index: int) -> Repository:
    full_name = f"{owner}/{name}"
    repo = db.scalar(
        select(Repository).where(
            Repository.organization_id == organization_id,
            Repository.full_name == full_name,
        )
    )
    if repo:
        # Clear existing scans so re-running yields a clean, known data set.
        for scan in list(repo.scans):
            db.delete(scan)
        repo.default_branch = default_branch
        repo.is_active = True
        db.flush()
        return repo

    repo = Repository(
        organization_id=organization_id,
        github_repository_id=GITHUB_REPO_ID_BASE + index,
        owner=owner,
        name=name,
        full_name=full_name,
        default_branch=default_branch,
        is_active=True,
    )
    db.add(repo)
    db.flush()
    return repo


def _make_sha(rng: random.Random) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(40))


def _seed_scans_for_repo(db, repo: Repository, path_root: str, now: datetime, rng: random.Random) -> int:
    # Each repo gets a rotated subset of the blueprints for variety.
    offset = rng.randint(0, len(SCAN_BLUEPRINTS) - 1)
    count = rng.randint(4, len(SCAN_BLUEPRINTS))
    created = 0
    for i in range(count):
        bp = SCAN_BLUEPRINTS[(offset + i) % len(SCAN_BLUEPRINTS)]
        pr_number = 100 + i
        days_ago = rng.randint(0, 29)
        hours = rng.randint(0, 23)
        created_at = now - timedelta(days=days_ago, hours=hours)

        status: ScanStatus = bp["status"]
        is_done = status in (ScanStatus.COMPLETED, ScanStatus.FAILED)
        is_completed = status == ScanStatus.COMPLETED

        findings = _build_findings(bp["findings"], path_root)
        score = bp["score"] if is_completed else None
        level = _risk_level_for(score) if score is not None else None

        report: dict = {}
        summary = None
        if is_completed:
            level = level or RiskLevel.LOW
            report = {
                "ai_review_markdown": _ai_review_markdown(bp["title"], level, bp["highlights"]),
                "ai_review": {"verdict": level.value, "highlights": bp["highlights"]},
            }
            summary = bp["highlights"][0] if bp["highlights"] else "Scan completed with no notable findings."

        started_at = created_at + timedelta(seconds=8) if status != ScanStatus.QUEUED else None
        completed_at = created_at + timedelta(minutes=rng.randint(1, 4)) if is_done else None
        failure_reason = (
            "Worker timed out while cloning the repository. Retried and routed to the dead-letter queue."
            if status == ScanStatus.FAILED
            else None
        )

        scan = PullRequestScan(
            organization_id=repo.organization_id,
            repository_id=repo.id,
            github_pr_number=pr_number,
            github_pr_url=f"https://github.com/{repo.full_name}/pull/{pr_number}",
            title=bp["title"],
            head_sha=_make_sha(rng),
            base_sha=_make_sha(rng),
            github_check_run_id=(GITHUB_REPO_ID_BASE + pr_number) if is_done else None,
            status=status,
            trigger="webhook",
            files_changed=bp["files"],
            lines_added=bp["added"],
            lines_deleted=bp["deleted"],
            risk_score=score,
            risk_level=level,
            summary=summary,
            failure_reason=failure_reason,
            semgrep_findings=findings["semgrep_findings"],
            ai_findings=findings["ai_findings"],
            company_rule_violations=findings["company_rule_violations"],
            architecture_violations=findings["architecture_violations"],
            report=report,
            started_at=started_at,
            completed_at=completed_at,
            created_at=created_at,
            updated_at=completed_at or started_at or created_at,
        )
        db.add(scan)
        created += 1
    return created


def _delete_demo_data(db, organization_id) -> None:
    repos = db.scalars(
        select(Repository).where(Repository.organization_id == organization_id)
    ).all()
    for repo in repos:
        db.delete(repo)
    db.flush()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed CodeDNA AI demo data.")
    parser.add_argument("--email", default=os.getenv("DEMO_EMAIL", DEFAULT_EMAIL))
    parser.add_argument("--password", default=os.getenv("DEMO_PASSWORD", DEFAULT_PASSWORD))
    parser.add_argument("--full-name", default=os.getenv("DEMO_FULL_NAME", DEFAULT_FULL_NAME))
    parser.add_argument("--organization-name", default=os.getenv("DEMO_ORG_NAME", DEFAULT_ORG_NAME))
    parser.add_argument("--organization-slug", default=os.getenv("DEMO_ORG_SLUG", DEFAULT_ORG_SLUG))
    parser.add_argument("--reset", action="store_true", help="Delete existing demo repositories/scans first.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rng = random.Random(SEED)
    now = datetime.now(timezone.utc)

    db = SessionLocal()
    try:
        user, created = AuthService(db).create_or_reset_admin_user(
            email=args.email,
            password=args.password,
            full_name=args.full_name,
            organization_name=args.organization_name,
            organization_slug=args.organization_slug,
        )
        organization = db.get(Organization, user.organization_id)
        assert organization is not None

        if args.reset:
            _delete_demo_data(db, organization.id)

        total_repos = 0
        total_scans = 0
        for index, (name, branch, path_root) in enumerate(REPOSITORIES):
            repo = _ensure_repository(db, organization.id, DEMO_OWNER, name, branch, index)
            total_repos += 1
            total_scans += _seed_scans_for_repo(db, repo, path_root, now, rng)

        db.commit()

        action = "created" if created else "reset"
        print(f"Demo admin user {action}: {user.email}")
        print(f"Password: {args.password}")
        print(f"Organization: {organization.name} ({organization.slug})")
        print(f"Repositories seeded: {total_repos}")
        print(f"Scans seeded: {total_scans}")
        return 0
    except SQLAlchemyError:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
