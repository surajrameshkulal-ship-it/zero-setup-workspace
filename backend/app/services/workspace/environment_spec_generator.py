"""Environment Specification Generator (Phase 11, Step 2).

Converts a repository's Setup Intent (plus Repository DNA) into a normalized,
executable-later EnvironmentSpec — a blueprint for how CodeDNA would prepare and
run the project in a future, separately gated step.

This step does NOT launch anything, execute repository code, install
dependencies, or make network calls beyond the read-only GitHub manifest fetch
already performed for the Setup Intent. Only environment variable names are
recorded (never values).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError
from app.models.environment_spec import EnvironmentSpec
from app.models.repository import Repository
from app.models.setup_intent import SetupIntent
from app.services.audit_service import AuditService
from app.services.repository_dna_service import RepositoryDNAService

logger = logging.getLogger(__name__)

LANGUAGE_PRIORITY = [
    "Python", "TypeScript", "JavaScript", "Go", "Rust", "Java", "Kotlin",
    "Ruby", "PHP", "C#", "Swift", "HTML", "CSS",
]
RUNTIME_BY_LANGUAGE = {
    "Python": "CPython",
    "TypeScript": "Node.js",
    "JavaScript": "Node.js",
    "Go": "Go",
    "Rust": "Rust",
    "Java": "JVM",
    "Kotlin": "JVM",
    "Ruby": "Ruby",
    "PHP": "PHP",
    "C#": ".NET",
    "Swift": "Swift",
    "HTML": "Browser",
    "CSS": "Browser",
}
STATIC_FRAMEWORKS = {"Static Website", "Static Site"}
# Frameworks that define how the app runs (preferred as the primary framework).
APP_FRAMEWORK_PRIORITY = [
    "Next.js", "FastAPI", "Django", "Flask", "Express", "NestJS", "Fastify",
    "Starlette", "Spring Boot", "Gin", "Echo", "Fiber", "Actix Web", "Axum",
    "Rocket", "Laravel", "Symfony", "Ruby on Rails", "Sinatra",
    "Angular", "Vue", "Svelte", "React", "Static Website",
]
SERVICE_DEFAULT_PORTS = {
    5432: "PostgreSQL", 3306: "MySQL", 6379: "Redis", 27017: "MongoDB",
    5672: "RabbitMQ", 9092: "Kafka", 11211: "Memcached",
}
DEFAULT_APP_PORT = {
    "Next.js": 3000, "React": 3000, "Express": 3000, "NestJS": 3000,
    "FastAPI": 8000, "Django": 8000, "Flask": 5000, "Spring Boot": 8080,
    "Gin": 8080, "Echo": 8080, "Fiber": 3000, "Laravel": 8000,
    "Ruby on Rails": 3000, "Static Website": 8000,
}
ENV_REQUIRED_HINTS = ("secret", "key", "token", "password", "passwd", "url", "dsn", "database", "host", "credential", "api_key")


class EnvironmentSpecGenerator:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    # -- queries ---------------------------------------------------------------

    def get_for_repository(self, repository_id: uuid.UUID, organization_id: uuid.UUID) -> EnvironmentSpec:
        spec = self._fetch(repository_id, organization_id)
        if not spec:
            raise NotFoundError("Environment spec not found")
        return spec

    def get_optional(self, repository_id: uuid.UUID, organization_id: uuid.UUID) -> EnvironmentSpec | None:
        return self._fetch(repository_id, organization_id)

    def _fetch(self, repository_id: uuid.UUID, organization_id: uuid.UUID) -> EnvironmentSpec | None:
        return self.db.scalar(
            select(EnvironmentSpec).where(
                EnvironmentSpec.repository_id == repository_id,
                EnvironmentSpec.organization_id == organization_id,
            )
        )

    # -- command ---------------------------------------------------------------

    def generate(
        self,
        *,
        repository_id: uuid.UUID,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        setup_intent: SetupIntent | None = None,
    ) -> EnvironmentSpec:
        repository = self._require_repository(repository_id, organization_id)
        intent = setup_intent or self.db.scalar(
            select(SetupIntent).where(
                SetupIntent.repository_id == repository_id,
                SetupIntent.organization_id == organization_id,
            )
        )
        if intent is None:
            raise AppError("No setup intent found. Analyze the repository setup first.")

        dna = RepositoryDNAService(self.db).get_optional(repository_id, organization_id)
        fields = self.build_spec(repository, intent, dna)

        spec = self.db.scalar(select(EnvironmentSpec).where(EnvironmentSpec.repository_id == repository.id))
        if spec is None:
            spec = EnvironmentSpec(organization_id=organization_id, repository_id=repository.id)
            self.db.add(spec)
        for key, value in fields.items():
            setattr(spec, key, value)

        self.db.flush()
        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="environment_spec_generated",
            target_type="repository",
            target_id=str(repository.id),
            metadata={"strategy": fields["container_strategy"], "confidence": fields["confidence_score"]},
        )
        self.db.commit()
        self.db.refresh(spec)
        return spec

    # -- build -----------------------------------------------------------------

    def build_spec(self, repository: Repository, intent: SetupIntent, dna: Any | None) -> dict:
        assumptions: list[str] = []
        missing: list[str] = []
        warnings: list[str] = []

        languages = list(intent.languages or [])
        primary_language = self._primary(languages, LANGUAGE_PRIORITY)
        if not primary_language:
            warnings.append("Could not determine a primary language.")
        runtime_name = RUNTIME_BY_LANGUAGE.get(primary_language or "", None)
        runtime_version = intent.runtime_version
        if not runtime_version:
            missing.append("Runtime version is not pinned; the latest stable runtime will be assumed.")

        framework = self._primary(list(intent.frameworks or []), APP_FRAMEWORK_PRIORITY)
        if intent.frameworks and len(intent.frameworks) > 1:
            assumptions.append(f"Multiple frameworks detected; using '{framework}' as primary.")
        # A static website runs in the browser, served by any static file server.
        if framework in STATIC_FRAMEWORKS:
            runtime_name = "Browser"
            if not primary_language:
                primary_language = "HTML"
            assumptions.append("Detected a static website; it can be served by any static file server.")

        # Commands
        install = intent.install_command
        if not install:
            missing.append("No install command detected.")
        if not (intent.dev_command or intent.prod_command):
            missing.append("No run (dev/production) command detected.")
        if not intent.test_command:
            missing.append("No test command detected.")

        # Ports
        ports = [int(p) for p in (intent.ports or [])]
        service_ports = sorted([p for p in ports if p in SERVICE_DEFAULT_PORTS])
        app_ports = sorted([p for p in ports if p not in SERVICE_DEFAULT_PORTS])
        if not app_ports and framework in DEFAULT_APP_PORT:
            app_ports = [DEFAULT_APP_PORT[framework]]
            assumptions.append(f"No app port detected; assuming default {app_ports[0]} for {framework}.")

        # Health check command
        health_endpoint = intent.health_check_endpoint
        health_command = None
        if health_endpoint and app_ports:
            health_command = f"curl -fsS http://localhost:{app_ports[0]}{health_endpoint}"

        # Environment variables (names + required heuristic)
        env_vars = [{"name": name, "required": self._is_required(name)} for name in (intent.env_vars or [])]
        missing_env_example = ".env.example" not in (intent.sources_analyzed or [])
        if missing_env_example:
            missing.append("No .env.example found; required environment variables may be incomplete.")

        # Container strategy
        docker = intent.docker or {}
        docker_files = docker.get("files", []) if isinstance(docker, dict) else []
        native = bool(install and (intent.dev_command or intent.prod_command))
        has_compose = "docker-compose" in docker_files
        has_dockerfile = "Dockerfile" in docker_files
        if has_compose and native:
            strategy = "hybrid"
        elif has_compose:
            strategy = "docker-compose"
        elif has_dockerfile:
            strategy = "docker"
        elif native:
            strategy = "native"
        elif framework in STATIC_FRAMEWORKS:
            strategy = "static"
        else:
            strategy = "unknown"
            warnings.append("Could not determine a container/runtime strategy.")

        databases = list(intent.databases or [])
        caches = list(intent.caches or [])
        queues = list(intent.queues or [])

        workspace_requirements = self._estimate_resources(framework, databases, caches, queues)

        safety = {
            "no_secrets": True,
            "no_execution": True,
            "no_dependency_installation": True,
            "network": "read-only GitHub manifest fetch only",
            "org_isolated": True,
        }

        confidence = round(min(1.0, max(0.0, (intent.confidence_score or 0.0) - (0.1 if strategy == "unknown" else 0.0))), 2)

        return {
            "primary_language": primary_language,
            "runtime_name": runtime_name,
            "runtime_version": runtime_version,
            "package_manager": intent.package_manager,
            "framework": framework,
            "install_command": install,
            "dev_command": intent.dev_command,
            "prod_command": intent.prod_command,
            "build_command": intent.build_command,
            "test_command": intent.test_command,
            "lint_command": intent.lint_command,
            "health_check_command": health_command,
            "databases": databases,
            "caches": caches,
            "queues": queues,
            "external_services": list(intent.external_services or []),
            "app_ports": app_ports,
            "service_ports": service_ports,
            "health_check_endpoint": health_endpoint,
            "env_vars": env_vars,
            "missing_env_example": missing_env_example,
            "container_strategy": strategy,
            "workspace_requirements": workspace_requirements,
            "safety": safety,
            "confidence_score": confidence,
            "assumptions": assumptions,
            "missing_information": missing,
            "warnings": warnings,
        }

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _primary(values: list[str], priority: list[str]) -> str | None:
        for candidate in priority:
            if candidate in values:
                return candidate
        return values[0] if values else None

    @staticmethod
    def _is_required(name: str) -> bool:
        lowered = name.lower()
        return any(hint in lowered for hint in ENV_REQUIRED_HINTS)

    @staticmethod
    def _estimate_resources(framework: str | None, databases: list, caches: list, queues: list) -> dict:
        cpu = 1
        memory_mb = 1024
        disk_mb = 2048
        volumes: list[str] = []

        if framework in ("Next.js", "Angular", "Nuxt"):
            memory_mb = max(memory_mb, 2048)  # JS build steps are memory-hungry
        for db in databases:
            memory_mb += 512
            disk_mb += 2048
            volumes.append(f"{db.lower().replace(' ', '-')}-data")
        if caches:
            memory_mb += 256
        if queues:
            memory_mb += 256

        return {
            "cpu": cpu,
            "memory_mb": min(memory_mb, 8192),
            "disk_mb": min(disk_mb, 20480),
            "network_access": True,  # required later to install dependencies
            "persistent_volumes": volumes,
        }

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
