"""Workspace Builder (Phase 11, Step 3).

Converts an EnvironmentSpec (plus Setup Intent and Repository DNA) into a
complete, reproducible WorkspaceBlueprint describing everything needed to launch
the project LATER.

Planning/generation only. This never launches containers, executes repository
code, installs dependencies, runs Docker, starts processes, creates cloud
resources, modifies the repository, or exposes secrets (variable names only).
All sequences are execution *plans*, not runs. Existing files are never
overwritten — proposed assets are marked as such.
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
from app.models.workspace_blueprint import WorkspaceBlueprint
from app.services.audit_service import AuditService
from app.services.repository_dna_service import RepositoryDNAService

logger = logging.getLogger(__name__)

JS_RUNTIMES = {"Node.js"}
PY_RUNTIMES = {"CPython", "Python"}


class WorkspaceBuilder:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    # -- queries ---------------------------------------------------------------

    def get_for_repository(self, repository_id: uuid.UUID, organization_id: uuid.UUID) -> WorkspaceBlueprint:
        bp = self._fetch(repository_id, organization_id)
        if not bp:
            raise NotFoundError("Workspace blueprint not found")
        return bp

    def get_optional(self, repository_id: uuid.UUID, organization_id: uuid.UUID) -> WorkspaceBlueprint | None:
        return self._fetch(repository_id, organization_id)

    def _fetch(self, repository_id: uuid.UUID, organization_id: uuid.UUID) -> WorkspaceBlueprint | None:
        return self.db.scalar(
            select(WorkspaceBlueprint).where(
                WorkspaceBlueprint.repository_id == repository_id,
                WorkspaceBlueprint.organization_id == organization_id,
            )
        )

    # -- command ---------------------------------------------------------------

    def generate(
        self,
        *,
        repository_id: uuid.UUID,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        environment_spec: EnvironmentSpec | None = None,
    ) -> WorkspaceBlueprint:
        repository = self._require_repository(repository_id, organization_id)
        spec = environment_spec or self.db.scalar(
            select(EnvironmentSpec).where(
                EnvironmentSpec.repository_id == repository_id,
                EnvironmentSpec.organization_id == organization_id,
            )
        )
        if spec is None:
            raise AppError("No environment spec found. Generate the environment spec first.")

        setup_intent = self.db.scalar(
            select(SetupIntent).where(
                SetupIntent.repository_id == repository_id,
                SetupIntent.organization_id == organization_id,
            )
        )
        dna = RepositoryDNAService(self.db).get_optional(repository_id, organization_id)

        fields = self.build_blueprint(repository, spec, setup_intent, dna)

        bp = self.db.scalar(select(WorkspaceBlueprint).where(WorkspaceBlueprint.repository_id == repository.id))
        if bp is None:
            bp = WorkspaceBlueprint(organization_id=organization_id, repository_id=repository.id)
            self.db.add(bp)
        for key, value in fields.items():
            setattr(bp, key, value)

        self.db.flush()
        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="workspace_blueprint_generated",
            target_type="repository",
            target_id=str(repository.id),
            metadata={"readiness_score": fields["readiness_score"]},
        )
        self.db.commit()
        self.db.refresh(bp)
        return bp

    # -- build -----------------------------------------------------------------

    def build_blueprint(
        self, repository: Repository, spec: EnvironmentSpec, setup_intent: SetupIntent | None, dna: Any | None
    ) -> dict:
        sources = set(getattr(setup_intent, "sources_analyzed", None) or [])
        important = list(getattr(dna, "important_files", None) or [])
        has_readme = "README.md" in sources or any("readme" in p.lower() for p in important)
        has_env_example = ".env.example" in sources and not spec.missing_env_example
        is_js = spec.runtime_name in JS_RUNTIMES
        is_py = spec.runtime_name in PY_RUNTIMES
        env_names = [e.get("name") for e in (spec.env_vars or []) if isinstance(e, dict) and e.get("name")]
        docker_files = (
            (setup_intent.docker or {}).get("files", []) if setup_intent and isinstance(setup_intent.docker, dict) else []
        )
        has_dockerfile = "Dockerfile" in docker_files
        has_compose = "docker-compose" in docker_files

        structure = self._structure(repository, important, is_js, is_py)
        environment_files = self._environment_files(env_names, has_env_example, spec)
        docker_assets = self._docker_assets(has_dockerfile, has_compose, spec)
        ide_assets = self._ide_assets(is_js, is_py)
        startup_plan = self._startup_plan(spec, has_compose)
        resources = self._resources(spec)
        warnings = self._warnings(spec, has_readme, has_env_example, has_dockerfile or has_compose)
        score, recommendations = self._readiness(spec, has_readme, has_env_example, has_dockerfile or has_compose)

        return {
            "language": spec.primary_language,
            "runtime": spec.runtime_name,
            "runtime_version": spec.runtime_version,
            "package_manager": spec.package_manager,
            "framework": spec.framework,
            "workspace_structure": structure,
            "environment_files": environment_files,
            "docker_assets": docker_assets,
            "ide_assets": ide_assets,
            "startup_plan": startup_plan,
            "workspace_resources": resources,
            "readiness_score": score,
            "recommendations": recommendations,
            "warnings": warnings,
            "safety": {
                "read_only_generation": True,
                "no_code_execution": True,
                "no_dependency_installation": True,
                "no_container_creation": True,
                "no_repository_modification": True,
                "no_secret_exposure": True,
                "org_isolated": True,
            },
        }

    # -- structure -------------------------------------------------------------

    @staticmethod
    def _structure(repository: Repository, important: list[str], is_js: bool, is_py: bool) -> dict:
        top_dirs = sorted({p.split("/")[0] for p in important if "/" in p})
        if is_js:
            source = [d for d in ["src", "app", "pages", "components", "lib"]]
            tests = ["__tests__", "tests"]
            generated = [".next", "dist", "build", "node_modules", "coverage"]
        elif is_py:
            source = [d for d in ["app", "src"]]
            tests = ["tests", "test"]
            generated = ["__pycache__", ".pytest_cache", ".venv", "dist", "build"]
        else:
            source = ["src"]
            tests = ["tests"]
            generated = ["dist", "build"]
        # Prefer observed top-level dirs where available.
        observed_source = [d for d in top_dirs if d in source]
        return {
            "project_root": ".",
            "source_directories": observed_source or source,
            "test_directories": tests,
            "documentation_directories": ["docs"],
            "configuration_directories": [".github", "config"],
            "generated_directories": generated,
            "ignored_directories": sorted(set(generated + [".git", ".venv", "node_modules"])),
        }

    # -- environment files -----------------------------------------------------

    @staticmethod
    def _environment_files(env_names: list[str], has_env_example: bool, spec: EnvironmentSpec) -> list[dict]:
        files = [
            {
                "name": ".env.example",
                "action": "existing" if has_env_example else "generate",
                "purpose": "Document required environment variable names (no values).",
                "variable_names": env_names,
            },
            {
                "name": ".env",
                "action": "generate",
                "purpose": "Local environment values (gitignored). Values are never generated or stored.",
                "variable_names": env_names,
            },
            {
                "name": ".env.local",
                "action": "generate",
                "purpose": "Local overrides (e.g. frontend NEXT_PUBLIC_* values).",
                "variable_names": [n for n in env_names if n.startswith("NEXT_PUBLIC_")] or env_names,
            },
            {
                "name": ".gitignore",
                "action": "append",
                "purpose": "Ensure local env, build output, and dependencies are ignored.",
                "variable_names": [],
                "entries": [".env", ".env.local", "node_modules/", ".venv/", "dist/", "build/", "__pycache__/"],
            },
        ]
        version_file = None
        if spec.runtime_name in JS_RUNTIMES and spec.runtime_version:
            version_file = {".nvmrc": spec.runtime_version}
        elif spec.runtime_name in PY_RUNTIMES and spec.runtime_version:
            version_file = {".python-version": spec.runtime_version}
        if version_file:
            name = next(iter(version_file))
            files.append(
                {
                    "name": name,
                    "action": "generate",
                    "purpose": "Pin the runtime version for reproducibility.",
                    "variable_names": [],
                }
            )
        return files

    # -- docker assets ---------------------------------------------------------

    @staticmethod
    def _docker_assets(has_dockerfile: bool, has_compose: bool, spec: EnvironmentSpec) -> list[dict]:
        needs_services = bool(spec.databases or spec.caches or spec.queues)
        assets = [
            {
                "name": "Dockerfile",
                "status": "existing" if has_dockerfile else "proposed",
                "description": "Container image for the application." + ("" if has_dockerfile else " Would be generated; existing files are never overwritten."),
            },
            {
                "name": "docker-compose.yml",
                "status": "existing" if has_compose else ("proposed" if needs_services or has_dockerfile else "not_recommended"),
                "description": "Orchestrates the app and its backing services.",
            },
            {
                "name": "devcontainer.json",
                "status": "proposed",
                "description": "Reproducible dev container definition for editors that support it.",
            },
            {
                "name": ".dockerignore",
                "status": "proposed" if (has_dockerfile or has_compose or needs_services) else "not_recommended",
                "description": "Keep build context small and free of secrets/build output.",
            },
        ]
        return assets

    # -- ide assets ------------------------------------------------------------

    @staticmethod
    def _ide_assets(is_js: bool, is_py: bool) -> list[dict]:
        if not (is_js or is_py):
            return []
        extensions = []
        if is_py:
            extensions = ["ms-python.python", "charliermarsh.ruff"]
        elif is_js:
            extensions = ["dbaeumer.vscode-eslint", "esbenp.prettier-vscode"]
        return [
            {"name": ".vscode/settings.json", "status": "proposed", "description": "Editor settings (format on save, interpreter)."},
            {"name": ".vscode/extensions.json", "status": "proposed", "description": "Recommended extensions.", "extensions": extensions},
            {"name": ".vscode/launch.json", "status": "proposed", "description": "Debug/run configurations."},
            {"name": ".vscode/tasks.json", "status": "proposed", "description": "Common tasks (install/build/test)."},
        ]

    # -- startup plan ----------------------------------------------------------

    @staticmethod
    def _startup_plan(spec: EnvironmentSpec, has_compose: bool) -> dict:
        install = []
        if has_compose and (spec.databases or spec.caches or spec.queues):
            install.append("docker compose up -d  # start backing services")
        if spec.install_command:
            install.append(spec.install_command)
        build = [spec.build_command] if spec.build_command else []
        start = [spec.dev_command or spec.prod_command] if (spec.dev_command or spec.prod_command) else []
        health = [spec.health_check_command] if spec.health_check_command else ["No health check detected."]
        shutdown = ["Stop the application process."]
        if has_compose:
            shutdown.append("docker compose down")
        return {
            "install_sequence": install or ["No install command detected."],
            "build_sequence": build or ["No build step required."],
            "start_sequence": start or ["No start command detected."],
            "health_check_sequence": health,
            "shutdown_sequence": shutdown,
            "note": "These are execution plans only; nothing is run by generating the blueprint.",
        }

    # -- resources -------------------------------------------------------------

    @staticmethod
    def _resources(spec: EnvironmentSpec) -> dict:
        wr = spec.workspace_requirements or {}
        return {
            "cpu": wr.get("cpu", 1),
            "ram_mb": wr.get("memory_mb", 1024),
            "disk_mb": wr.get("disk_mb", 2048),
            "network_access": wr.get("network_access", True),
            "volumes": wr.get("persistent_volumes", []),
            "services": list(spec.databases or []) + list(spec.caches or []) + list(spec.queues or []),
        }

    # -- readiness + warnings --------------------------------------------------

    @staticmethod
    def _readiness(spec: EnvironmentSpec, has_readme: bool, has_env_example: bool, has_docker: bool) -> tuple[int, list[str]]:
        checks = [
            (bool(spec.install_command), 20, "Add an install command/script."),
            (bool(spec.dev_command or spec.prod_command), 20, "Add a run (dev or production) command."),
            (bool(spec.package_manager), 15, "Declare a package manager / dependency manifest."),
            (bool(spec.test_command), 15, "Add a test command/script."),
            (has_docker, 10, "Add Docker support (Dockerfile/compose) for reproducible builds."),
            (bool(spec.health_check_endpoint), 10, "Expose a health-check endpoint (e.g. /health)."),
            (has_env_example, 10, "Add a .env.example documenting required variables."),
        ]
        score = sum(points for met, points, _ in checks if met)
        recommendations = [rec for met, _, rec in checks if not met]
        if not has_readme:
            recommendations.append("Add a README describing how to set up and run the project.")
        if not spec.runtime_version:
            recommendations.append("Pin the runtime version for reproducibility.")
        return score, recommendations

    @staticmethod
    def _warnings(spec: EnvironmentSpec, has_readme: bool, has_env_example: bool, has_docker: bool) -> list[str]:
        warnings: list[str] = []
        if not has_readme:
            warnings.append("Missing README.")
        if not has_env_example:
            warnings.append("Missing .env.example.")
        if not spec.test_command:
            warnings.append("No test command detected.")
        if not has_docker:
            warnings.append("No Docker support detected.")
        if not spec.runtime_version:
            warnings.append("Unknown runtime version.")
        if not spec.health_check_endpoint:
            warnings.append("Missing health-check endpoint.")
        return warnings

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
