from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.repository import Repository
from app.models.rule import ArchitectureRule, CompanyRule
from app.models.scan import PullRequestScan, ScanStatus

# Candidate dependency manifests, by ecosystem. Their actual contents are only
# fetched in a later (separately gated) execution phase — here we record which
# ones to look for.
DEPENDENCY_MANIFEST_CANDIDATES = [
    "pyproject.toml",
    "requirements.txt",
    "Pipfile",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
]


class RepositoryContextService:
    """Builds a normalized, read-only repository context object.

    Everything here is metadata derived from CodeDNA's own database (rules,
    scans, AI reviews). It does NOT clone the repository or generate code.
    Fields that require a live GitHub fetch are returned as null/empty with a
    note so a later, separately gated phase can populate them.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def build(self, *, organization_id: uuid.UUID, repository: Repository | None) -> dict:
        repository_id = repository.id if repository else None

        company_rules = self.db.scalars(
            select(CompanyRule).where(
                CompanyRule.organization_id == organization_id,
                CompanyRule.is_active.is_(True),
            )
        ).all()
        architecture_rules = self.db.scalars(
            select(ArchitectureRule).where(
                ArchitectureRule.organization_id == organization_id,
                ArchitectureRule.is_active.is_(True),
            )
        ).all()

        latest_scans = self._latest_scans(organization_id, repository_id)
        latest_completed = self._latest_completed_scan(organization_id, repository_id)

        recent_semgrep_findings: list = []
        latest_ai_review: str | None = None
        if latest_completed is not None:
            recent_semgrep_findings = list(latest_completed.semgrep_findings or [])
            latest_ai_review = latest_completed.ai_review_markdown

        return {
            "repository": (
                {
                    "full_name": repository.full_name,
                    "owner": repository.owner,
                    "name": repository.name,
                    "default_branch": repository.default_branch,
                    "is_active": bool(repository.is_active),
                    "github_linked": repository.github_installation_id is not None,
                }
                if repository
                else None
            ),
            "architecture_rules": [
                {
                    "name": rule.name,
                    "description": rule.description,
                    "source_path_pattern": rule.source_path_pattern,
                    "forbidden_import_pattern": rule.forbidden_import_pattern,
                    "severity": rule.severity.value,
                }
                for rule in architecture_rules
            ],
            "company_rules": [
                {
                    "name": rule.name,
                    "description": rule.description,
                    "rule_type": rule.rule_type.value,
                    "pattern": rule.pattern,
                    "severity": rule.severity.value,
                }
                for rule in company_rules
            ],
            "latest_scans": [
                {
                    "pr_number": scan.github_pr_number,
                    "title": scan.title,
                    "status": scan.status.value,
                    "risk_level": scan.risk_level.value if scan.risk_level else None,
                    "risk_score": scan.risk_score,
                    "findings_count": scan.findings_count,
                    "created_at": scan.created_at.isoformat() if scan.created_at else None,
                }
                for scan in latest_scans
            ],
            "recent_semgrep_findings": recent_semgrep_findings,
            "latest_ai_review": latest_ai_review,
            "dependency_files": {
                "candidates": list(DEPENDENCY_MANIFEST_CANDIDATES),
                "resolved": [],
                "note": "Manifest contents are fetched in a later execution phase.",
            },
            "readme": None,
            "language": None,
            "framework": None,
            "structure": [],
            "notes": [
                "Repository structure, README, and language/framework detection "
                "require a live GitHub fetch performed in a later, separately "
                "gated execution phase. No source code is read or generated here.",
            ],
        }

    # -- helpers ---------------------------------------------------------------

    def _latest_scans(
        self, organization_id: uuid.UUID, repository_id: uuid.UUID | None, limit: int = 5
    ) -> list[PullRequestScan]:
        query = (
            select(PullRequestScan)
            .where(PullRequestScan.organization_id == organization_id)
            .order_by(PullRequestScan.created_at.desc())
            .limit(limit)
        )
        if repository_id:
            query = query.where(PullRequestScan.repository_id == repository_id)
        return list(self.db.scalars(query).all())

    def _latest_completed_scan(
        self, organization_id: uuid.UUID, repository_id: uuid.UUID | None
    ) -> PullRequestScan | None:
        query = (
            select(PullRequestScan)
            .where(
                PullRequestScan.organization_id == organization_id,
                PullRequestScan.status == ScanStatus.COMPLETED,
            )
            .order_by(PullRequestScan.created_at.desc())
            .limit(1)
        )
        if repository_id:
            query = query.where(PullRequestScan.repository_id == repository_id)
        return self.db.scalar(query)
