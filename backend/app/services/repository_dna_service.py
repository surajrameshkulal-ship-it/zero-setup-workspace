from __future__ import annotations

import logging
import os
import uuid
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.repository import Repository
from app.models.repository_dna import RepositoryDNA
from app.models.rule import ArchitectureRule
from app.models.scan import PullRequestScan, RiskLevel, ScanStatus
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)

EXT_LANGUAGE = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".cpp": "C++",
    ".c": "C",
    ".kt": "Kotlin",
    ".swift": "Swift",
    ".scala": "Scala",
    ".sql": "SQL",
    ".sh": "Shell",
}

# basename (lowercased) -> (category, label)
FILE_SIGNALS: dict[str, tuple[str, str]] = {
    "package.json": ("package_managers", "npm"),
    "package-lock.json": ("package_managers", "npm"),
    "yarn.lock": ("package_managers", "Yarn"),
    "pnpm-lock.yaml": ("package_managers", "pnpm"),
    "pyproject.toml": ("package_managers", "pip / poetry"),
    "requirements.txt": ("package_managers", "pip"),
    "pipfile": ("package_managers", "pipenv"),
    "go.mod": ("package_managers", "Go modules"),
    "cargo.toml": ("package_managers", "Cargo"),
    "pom.xml": ("package_managers", "Maven"),
    "build.gradle": ("package_managers", "Gradle"),
    "next.config.mjs": ("frameworks", "Next.js"),
    "next.config.js": ("frameworks", "Next.js"),
    "tailwind.config.ts": ("frameworks", "Tailwind CSS"),
    "tailwind.config.js": ("frameworks", "Tailwind CSS"),
    "dockerfile": ("docker", "Dockerfile"),
    "docker-compose.yml": ("docker", "docker-compose"),
    "docker-compose.yaml": ("docker", "docker-compose"),
    "pytest.ini": ("testing_tools", "pytest"),
    "conftest.py": ("testing_tools", "pytest"),
    "jest.config.js": ("testing_tools", "Jest"),
    "jest.config.ts": ("testing_tools", "Jest"),
    "vitest.config.ts": ("testing_tools", "Vitest"),
}

# substring (in lowercased path) -> (category, label)
PATH_SIGNALS: list[tuple[str, str, str]] = [
    ("/.github/workflows/", "cicd", "GitHub Actions"),
    (".gitlab-ci", "cicd", "GitLab CI"),
    ("alembic", "frameworks", "Alembic (migrations)"),
    ("celery", "queues", "Celery"),
    ("redis", "queues", "Redis"),
    ("psycopg", "databases", "PostgreSQL"),
    ("postgres", "databases", "PostgreSQL"),
    ("sqlalchemy", "databases", "SQLAlchemy"),
    ("mongo", "databases", "MongoDB"),
    ("mysql", "databases", "MySQL"),
    ("fastapi", "frameworks", "FastAPI"),
    ("/build.gradle", "build_tools", "Gradle"),
]

DEPENDENCY_MANIFESTS = {
    "pyproject.toml",
    "requirements.txt",
    "pipfile",
    "package.json",
    "go.mod",
    "cargo.toml",
    "pom.xml",
    "build.gradle",
}


class RepositoryDNAService:
    """Builds a read-only repository fingerprint from CodeDNA's own data.

    No cloning, no source reads, no Git writes. Signals are inferred from scan
    finding paths, architecture rules, and repository metadata.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    # -- queries ---------------------------------------------------------------

    def get_for_repository(self, repository_id: uuid.UUID, organization_id: uuid.UUID) -> RepositoryDNA:
        dna = self.db.scalar(
            select(RepositoryDNA).where(
                RepositoryDNA.repository_id == repository_id,
                RepositoryDNA.organization_id == organization_id,
            )
        )
        if not dna:
            raise NotFoundError("Repository DNA not found")
        return dna

    def get_optional(self, repository_id: uuid.UUID, organization_id: uuid.UUID) -> RepositoryDNA | None:
        return self.db.scalar(
            select(RepositoryDNA).where(
                RepositoryDNA.repository_id == repository_id,
                RepositoryDNA.organization_id == organization_id,
            )
        )

    # -- command ---------------------------------------------------------------

    def generate(
        self,
        *,
        repository_id: uuid.UUID,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
    ) -> RepositoryDNA:
        repository = self._require_repository(repository_id, organization_id)
        fingerprint = self.build_fingerprint(organization_id, repository)

        dna = self.db.scalar(
            select(RepositoryDNA).where(RepositoryDNA.repository_id == repository.id)
        )
        if dna is None:
            dna = RepositoryDNA(organization_id=organization_id, repository_id=repository.id)
            self.db.add(dna)

        for key, value in fingerprint.items():
            setattr(dna, key, value)

        self.db.flush()
        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="repository_dna_generated",
            target_type="repository",
            target_id=str(repository.id),
            metadata={"language_count": len(fingerprint.get("languages", []))},
        )
        self.db.commit()
        self.db.refresh(dna)
        return dna

    # -- fingerprinting --------------------------------------------------------

    def build_fingerprint(self, organization_id: uuid.UUID, repository: Repository) -> dict:
        scans = list(
            self.db.scalars(
                select(PullRequestScan)
                .where(
                    PullRequestScan.organization_id == organization_id,
                    PullRequestScan.repository_id == repository.id,
                )
                .order_by(PullRequestScan.created_at.desc())
                .limit(50)
            ).all()
        )
        architecture_rules = list(
            self.db.scalars(
                select(ArchitectureRule).where(ArchitectureRule.organization_id == organization_id)
            ).all()
        )

        paths = self._collect_paths(scans, architecture_rules)

        buckets: dict[str, set[str]] = {
            "languages": set(),
            "frameworks": set(),
            "package_managers": set(),
            "databases": set(),
            "queues": set(),
            "testing_tools": set(),
            "build_tools": set(),
            "cicd": set(),
            "security_tools": set(),
        }
        docker_files: set[str] = set()
        important_files: Counter = Counter()

        for raw in paths:
            path = raw.lower()
            basename = os.path.basename(path)

            ext = os.path.splitext(basename)[1]
            if ext in EXT_LANGUAGE:
                buckets["languages"].add(EXT_LANGUAGE[ext])

            if basename in FILE_SIGNALS:
                category, label = FILE_SIGNALS[basename]
                if category == "docker":
                    docker_files.add(label)
                else:
                    buckets[category].add(label)
                important_files[raw] += 5

            for needle, category, label in PATH_SIGNALS:
                if needle in path:
                    if category in buckets:
                        buckets[category].add(label)

            if "test" in path or "spec" in path:
                important_files[raw] += 1

        # CodeDNA itself runs Semgrep + AI review on every scan.
        if scans:
            buckets["security_tools"].add("Semgrep (via CodeDNA)")
            buckets["security_tools"].add("CodeDNA AI review")

        # "test" directories imply a testing setup even without a config file.
        if any("test" in p.lower() or "spec" in p.lower() for p in paths) and not buckets["testing_tools"]:
            buckets["testing_tools"].add("Automated tests detected")

        important = [path for path, _ in important_files.most_common(15)]

        return {
            "languages": sorted(buckets["languages"]),
            "frameworks": sorted(buckets["frameworks"]),
            "package_managers": sorted(buckets["package_managers"]),
            "databases": sorted(buckets["databases"]),
            "queues": sorted(buckets["queues"]),
            "testing_tools": sorted(buckets["testing_tools"]),
            "build_tools": sorted(buckets["build_tools"]),
            "cicd": sorted(buckets["cicd"]),
            "docker": {"present": bool(docker_files), "files": sorted(docker_files)},
            "security_tools": sorted(buckets["security_tools"]),
            "important_files": important,
            "architecture_summary": self._architecture_summary(architecture_rules, paths),
            "dependency_summary": self._dependency_summary(paths),
            "repository_health": self._repository_health(scans),
            "risk_notes": self._risk_notes(scans),
        }

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _collect_paths(scans: list[PullRequestScan], architecture_rules: list[ArchitectureRule]) -> list[str]:
        paths: list[str] = []
        for scan in scans:
            for collection in (
                scan.semgrep_findings,
                scan.ai_findings,
                scan.company_rule_violations,
                scan.architecture_violations,
            ):
                for finding in collection or []:
                    if isinstance(finding, dict) and finding.get("path"):
                        paths.append(str(finding["path"]))
        for rule in architecture_rules:
            if rule.source_path_pattern:
                paths.append(str(rule.source_path_pattern).replace("**", "").replace("*", ""))
        return [p for p in paths if p]

    @staticmethod
    def _architecture_summary(architecture_rules: list[ArchitectureRule], paths: list[str]) -> str:
        top_dirs = Counter(p.split("/")[0] for p in paths if "/" in p)
        layers = ", ".join(name for name, _ in top_dirs.most_common(5)) or "not yet determined"
        rule_part = (
            f"{len(architecture_rules)} architecture rule(s) are enforced."
            if architecture_rules
            else "No architecture rules are defined."
        )
        return (
            f"Observed top-level areas: {layers}. {rule_part} "
            "Detailed structure requires a later, separately gated repository fetch."
        )

    @staticmethod
    def _dependency_summary(paths: list[str]) -> dict:
        manifests = sorted({os.path.basename(p) for p in paths if os.path.basename(p).lower() in DEPENDENCY_MANIFESTS})
        return {
            "manifests_detected": manifests,
            "note": (
                "Dependency manifests detected from scan history; full dependency "
                "resolution requires a later execution-phase fetch."
            ),
        }

    @staticmethod
    def _repository_health(scans: list[PullRequestScan]) -> dict:
        total = len(scans)
        if total == 0:
            return {"score": None, "status": "no_data", "notes": ["No scans recorded for this repository yet."]}

        completed = sum(1 for s in scans if s.status == ScanStatus.COMPLETED)
        failed = sum(1 for s in scans if s.status == ScanStatus.FAILED)
        high_risk = sum(1 for s in scans if s.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL))

        score = max(0, min(100, 100 - failed * 15 - high_risk * 10))
        status = "good" if score >= 80 else "fair" if score >= 50 else "poor"
        notes = [
            f"{total} scans analyzed ({completed} completed, {failed} failed).",
            f"{high_risk} scan(s) flagged high or critical risk.",
        ]
        return {"score": score, "status": status, "notes": notes}

    @staticmethod
    def _risk_notes(scans: list[PullRequestScan]) -> list[str]:
        notes: list[str] = []
        for scan in scans[:10]:
            if scan.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                notes.append(
                    f"PR #{scan.github_pr_number} ({scan.title or 'untitled'}) was "
                    f"{scan.risk_level.value} risk."
                )
            if scan.status == ScanStatus.FAILED:
                notes.append(f"PR #{scan.github_pr_number} scan failed: {scan.failure_reason or 'unknown error'}.")
        if not notes:
            notes.append("No elevated risk detected in recent scan history.")
        return notes

    def _require_repository(self, repository_id: uuid.UUID, organization_id: uuid.UUID) -> Repository:
        repository = self.db.scalar(
            select(Repository).where(
                Repository.id == repository_id,
                Repository.organization_id == organization_id,
            )
        )
        if not repository:
            raise NotFoundError("Repository not found")
        return repository
