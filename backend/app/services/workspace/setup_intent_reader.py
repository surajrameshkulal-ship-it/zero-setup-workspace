"""Setup Intent Reader (Phase 11, Step 1).

Infers how a repository should be built and run by reading its manifest files
(README, package.json, lockfiles, requirements.txt, pyproject.toml, Dockerfile,
docker-compose.yml, Makefile, .github/workflows/*, .env.example, Procfile).

Read-only and deterministic-first: repository code is never executed, and only
environment variable *names* are captured (never values). Repository DNA is
reused as a baseline. AI is reserved for genuinely ambiguous cases and is
optional (skipped when unavailable).
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import IntegrationError, NotFoundError
from app.integrations.github import GitHubIntegration
from app.models.github import GitHubInstallation
from app.models.repository import Repository
from app.models.setup_intent import SetupIntent
from app.services.audit_service import AuditService
from app.services.repository_dna_service import RepositoryDNAService

logger = logging.getLogger(__name__)

# Files to fetch for analysis.
MANIFEST_FILES = [
    "README.md",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "requirements.txt",
    "pyproject.toml",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Makefile",
    ".env.example",
    "Procfile",
]

JS_FRAMEWORKS = {
    "next": "Next.js",
    "react": "React",
    "vue": "Vue",
    "@angular/core": "Angular",
    "svelte": "Svelte",
    "express": "Express",
    "@nestjs/core": "NestJS",
    "fastify": "Fastify",
    "tailwindcss": "Tailwind CSS",
}
PY_FRAMEWORKS = {
    "fastapi": "FastAPI",
    "django": "Django",
    "flask": "Flask",
    "starlette": "Starlette",
}
DB_SIGNALS = {
    "postgres": "PostgreSQL",
    "psycopg": "PostgreSQL",
    "pg": "PostgreSQL",
    "mysql": "MySQL",
    "mariadb": "MariaDB",
    "mongo": "MongoDB",
    "mongoose": "MongoDB",
    "pymongo": "MongoDB",
    "sqlite": "SQLite",
}
CACHE_SIGNALS = {"redis": "Redis", "memcached": "Memcached"}
QUEUE_SIGNALS = {"celery": "Celery", "rabbitmq": "RabbitMQ", "amqp": "RabbitMQ", "kafka": "Kafka", "bullmq": "BullMQ", "sidekiq": "Sidekiq"}
SERVICE_SIGNALS = {"stripe": "Stripe", "sendgrid": "SendGrid", "twilio": "Twilio", "boto3": "AWS", "aws-sdk": "AWS", "openai": "OpenAI", "groq": "Groq"}


class SetupIntentReader:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    # -- queries ---------------------------------------------------------------

    def get_for_repository(self, repository_id: uuid.UUID, organization_id: uuid.UUID) -> SetupIntent:
        intent = self._fetch(repository_id, organization_id)
        if not intent:
            raise NotFoundError("Setup intent not found")
        return intent

    def get_optional(self, repository_id: uuid.UUID, organization_id: uuid.UUID) -> SetupIntent | None:
        return self._fetch(repository_id, organization_id)

    def _fetch(self, repository_id: uuid.UUID, organization_id: uuid.UUID) -> SetupIntent | None:
        return self.db.scalar(
            select(SetupIntent).where(
                SetupIntent.repository_id == repository_id,
                SetupIntent.organization_id == organization_id,
            )
        )

    # -- command ---------------------------------------------------------------

    def generate(
        self,
        *,
        repository_id: uuid.UUID,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        files: dict[str, str] | None = None,
        file_provider: Callable[[Repository], dict[str, str]] | None = None,
    ) -> SetupIntent:
        repository = self._require_repository(repository_id, organization_id)
        if files is None:
            provider = file_provider or GitHubManifestFileProvider(self.db)
            files = provider(repository)
        dna = RepositoryDNAService(self.db).get_optional(repository_id, organization_id)

        fields = self.build_intent(repository, files, dna)

        intent = self.db.scalar(select(SetupIntent).where(SetupIntent.repository_id == repository.id))
        if intent is None:
            intent = SetupIntent(organization_id=organization_id, repository_id=repository.id)
            self.db.add(intent)
        for key, value in fields.items():
            setattr(intent, key, value)

        self.db.flush()
        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="setup_intent_generated",
            target_type="repository",
            target_id=str(repository.id),
            metadata={"confidence": fields.get("confidence_score"), "sources": fields.get("sources_analyzed")},
        )
        self.db.commit()
        self.db.refresh(intent)
        return intent

    # -- inference -------------------------------------------------------------

    def build_intent(self, repository: Repository, files: dict[str, str], dna: Any | None) -> dict:
        by_name = {k.split("/")[-1].lower(): v for k, v in files.items()}
        all_text = "\n".join(files.values())

        languages: set[str] = set(getattr(dna, "languages", None) or [])
        frameworks: set[str] = set(getattr(dna, "frameworks", None) or [])
        databases: set[str] = set(getattr(dna, "databases", None) or [])
        caches: set[str] = set()
        queues: set[str] = set(getattr(dna, "queues", None) or [])
        services: set[str] = set()
        env_vars: set[str] = set()
        ports: set[int] = set()
        commands: dict[str, str | None] = {
            "install_command": None, "dev_command": None, "prod_command": None,
            "test_command": None, "build_command": None, "lint_command": None,
        }
        package_manager: str | None = None
        runtime_version: str | None = None

        # package.json
        pkg = self._parse_json(by_name.get("package.json"))
        if pkg is not None:
            languages.add("JavaScript")
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            for dep in deps:
                if dep in JS_FRAMEWORKS:
                    frameworks.add(JS_FRAMEWORKS[dep])
                self._classify_dep(dep, databases, caches, queues, services)
                if "typescript" in dep:
                    languages.add("TypeScript")
            scripts = pkg.get("scripts", {}) if isinstance(pkg.get("scripts"), dict) else {}
            commands["dev_command"] = self._npm(scripts, ["dev", "develop", "start:dev"])
            commands["prod_command"] = self._npm(scripts, ["start", "serve"])
            commands["build_command"] = self._npm(scripts, ["build"])
            commands["test_command"] = self._npm(scripts, ["test"])
            commands["lint_command"] = self._npm(scripts, ["lint"])
            engines = pkg.get("engines", {})
            if isinstance(engines, dict) and engines.get("node"):
                runtime_version = f"Node {engines['node']}"

        # package manager from lockfiles
        if "pnpm-lock.yaml" in by_name:
            package_manager = "pnpm"
        elif "yarn.lock" in by_name:
            package_manager = "yarn"
        elif "package-lock.json" in by_name or pkg is not None:
            package_manager = package_manager or "npm"

        # Python: requirements.txt / pyproject.toml
        req = by_name.get("requirements.txt")
        pyproject = by_name.get("pyproject.toml")
        py_deps_text = ""
        if req is not None:
            languages.add("Python")
            py_deps_text += req
        if pyproject is not None:
            languages.add("Python")
            py_deps_text += "\n" + pyproject
            requires = re.search(r'requires-python\s*=\s*["\']([^"\']+)["\']', pyproject)
            if requires:
                runtime_version = runtime_version or f"Python {requires.group(1)}"
            if "[tool.poetry]" in pyproject:
                package_manager = package_manager or "poetry"
        if py_deps_text:
            lowered = py_deps_text.lower()
            for key, label in PY_FRAMEWORKS.items():
                if key in lowered:
                    frameworks.add(label)
            self._classify_text(lowered, databases, caches, queues, services)
            package_manager = package_manager or "pip"
            if "pytest" in lowered:
                commands["test_command"] = commands["test_command"] or "python -m pytest"
            if "fastapi" in lowered:
                commands["dev_command"] = commands["dev_command"] or "uvicorn app.main:app --reload"
                commands["prod_command"] = commands["prod_command"] or "uvicorn app.main:app --host 0.0.0.0 --port 8000"
            if "django" in lowered:
                commands["dev_command"] = commands["dev_command"] or "python manage.py runserver"
            commands["install_command"] = commands["install_command"] or (
                "pip install -e ." if pyproject is not None else "pip install -r requirements.txt"
            )

        # default install for JS
        if pkg is not None:
            commands["install_command"] = commands["install_command"] or f"{package_manager or 'npm'} install"

        # Dockerfile
        dockerfile = by_name.get("dockerfile")
        docker_files: list[str] = []
        if dockerfile is not None:
            docker_files.append("Dockerfile")
            for m in re.finditer(r"(?im)^\s*EXPOSE\s+(\d+)", dockerfile):
                ports.add(int(m.group(1)))
            base = re.search(r"(?im)^\s*FROM\s+([^\s]+)", dockerfile)
            if base and not runtime_version:
                runtime_version = self._runtime_from_image(base.group(1))

        # docker-compose
        compose = by_name.get("docker-compose.yml") or by_name.get("docker-compose.yaml")
        if compose is not None:
            docker_files.append("docker-compose")
            lowered = compose.lower()
            self._classify_text(lowered, databases, caches, queues, services)
            for m in re.finditer(r"(\d{2,5}):(\d{2,5})", compose):
                ports.add(int(m.group(2)))

        # Makefile targets
        makefile = by_name.get("makefile")
        if makefile is not None:
            targets = set(re.findall(r"(?im)^([a-zA-Z0-9_-]+):", makefile))
            for target, slot in (("install", "install_command"), ("test", "test_command"),
                                  ("build", "build_command"), ("lint", "lint_command"),
                                  ("run", "prod_command"), ("dev", "dev_command")):
                if target in targets and not commands[slot]:
                    commands[slot] = f"make {target}"

        # Procfile
        procfile = by_name.get("procfile")
        if procfile is not None:
            web = re.search(r"(?im)^web:\s*(.+)$", procfile)
            if web and not commands["prod_command"]:
                commands["prod_command"] = web.group(1).strip()

        # .env.example -> variable names only
        env_example = by_name.get(".env.example")
        if env_example is not None:
            for line in env_example.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                line = line[len("export "):].strip() if line.lower().startswith("export ") else line
                if "=" in line:
                    name = line.split("=", 1)[0].strip()
                    if name and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                        env_vars.add(name)

        # CI/CD provider
        cicd_provider = None
        if any(k.startswith(".github/workflows/") for k in files):
            cicd_provider = "GitHub Actions"
        elif ".gitlab-ci.yml" in by_name:
            cicd_provider = "GitLab CI"
        elif by_name.get("dockerfile") and "circleci" in all_text.lower():
            cicd_provider = "CircleCI"

        # Health check endpoint
        health = None
        m = re.search(r"(/health[a-z]*|/healthz|/livez|/readyz)", all_text)
        if m:
            health = m.group(1)

        fields = {
            "languages": sorted(languages),
            "frameworks": sorted(frameworks),
            "package_manager": package_manager,
            "runtime_version": runtime_version,
            **commands,
            "env_vars": sorted(env_vars),
            "ports": sorted(ports),
            "databases": sorted(databases),
            "caches": sorted(caches),
            "queues": sorted(queues),
            "external_services": sorted(services),
            "docker": {"present": bool(docker_files), "files": docker_files},
            "cicd_provider": cicd_provider,
            "health_check_endpoint": health,
            "sources_analyzed": sorted(files.keys()),
            "notes": self._notes(files),
        }
        fields["confidence_score"] = self._confidence(fields)
        return fields

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _npm(scripts: dict, names: list[str]) -> str | None:
        for name in names:
            if name in scripts:
                return f"npm run {name}" if name not in ("start",) else "npm start"
        return None

    @staticmethod
    def _classify_dep(dep: str, databases, caches, queues, services) -> None:
        SetupIntentReader._classify_text(dep.lower(), databases, caches, queues, services)

    @staticmethod
    def _classify_text(text: str, databases, caches, queues, services) -> None:
        for key, label in DB_SIGNALS.items():
            if key in text:
                databases.add(label)
        for key, label in CACHE_SIGNALS.items():
            if key in text:
                caches.add(label)
        for key, label in QUEUE_SIGNALS.items():
            if key in text:
                queues.add(label)
        for key, label in SERVICE_SIGNALS.items():
            if key in text:
                services.add(label)

    @staticmethod
    def _runtime_from_image(image: str) -> str | None:
        image = image.lower()
        m = re.search(r"python:([0-9.]+)", image)
        if m:
            return f"Python {m.group(1)}"
        m = re.search(r"node:([0-9.]+)", image)
        if m:
            return f"Node {m.group(1)}"
        return None

    @staticmethod
    def _parse_json(text: str | None) -> dict | None:
        if not text:
            return None
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _notes(files: dict[str, str]) -> list[str]:
        present = {k.split("/")[-1].lower() for k in files}
        missing = [name for name in MANIFEST_FILES if name.lower() not in present]
        if not files:
            return ["No manifest files were available for analysis."]
        notes = [f"Analyzed {len(files)} manifest file(s); inference is read-only and code was never executed."]
        if missing:
            notes.append("Optional manifests not present: " + ", ".join(missing) + ".")
        return notes

    @staticmethod
    def _confidence(fields: dict) -> float:
        signals = [
            bool(fields["languages"]),
            bool(fields["package_manager"]),
            bool(fields["install_command"]),
            bool(fields["dev_command"] or fields["prod_command"]),
            bool(fields["build_command"] or fields["test_command"]),
            bool(fields["frameworks"]),
        ]
        return round(sum(signals) / len(signals), 2)

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


class GitHubManifestFileProvider:
    """Fetches the manifest files (and workflow files) read-only via the App token."""

    def __init__(self, db: Session, *, integration: GitHubIntegration | None = None) -> None:
        self.db = db
        self.gh = integration or GitHubIntegration()

    def __call__(self, repository: Repository) -> dict[str, str]:
        # Fatal: the repository must be connected to a GitHub installation.
        if repository.github_installation_id is None:
            raise IntegrationError("Repository is not connected to a GitHub installation.")
        installation = self.db.get(GitHubInstallation, repository.github_installation_id)
        if installation is None:
            raise IntegrationError("GitHub installation is missing for this repository.")

        # Fatal: token retrieval (invalid App credentials/installation) propagates.
        token = self.gh.get_installation_token(installation.installation_id)
        ref = repository.default_branch or "main"

        # Fatal: one repo-level call distinguishes "repo inaccessible" from
        # "file missing". If we can read the default branch, per-file 404s are
        # simply optional manifests that don't exist.
        try:
            self.gh.get_branch_sha(token=token, owner=repository.owner, repo=repository.name, branch=ref)
        except IntegrationError as exc:
            raise IntegrationError(
                f"Unable to access repository '{repository.full_name}' on GitHub. "
                "Check that the GitHub App is installed and has repository read access."
            ) from exc

        files: dict[str, str] = {}
        for path in MANIFEST_FILES:
            content = self._safe_get(token, repository, path, ref)
            if content is not None:
                files[path] = content
        # Workflow listing already tolerates a missing directory.
        for workflow_path in self.gh.list_directory(
            token=token, owner=repository.owner, repo=repository.name, path=".github/workflows", ref=ref
        ):
            content = self._safe_get(token, repository, workflow_path, ref)
            if content is not None:
                files[workflow_path] = content
        return files

    def _safe_get(self, token: str, repository: Repository, path: str, ref: str) -> str | None:
        """Fetch one optional manifest; a 404 (missing file) is not fatal."""
        try:
            return self.gh.get_file_content(
                token=token, owner=repository.owner, repo=repository.name, path=path, ref=ref
            )
        except IntegrationError:
            logger.info("setup_intent_manifest_missing", extra={"repository": repository.full_name, "path": path})
            return None
