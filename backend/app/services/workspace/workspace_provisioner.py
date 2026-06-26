"""Workspace Provisioner (Phase 11, Step 4).

Prepares everything required to run a project LATER from a WorkspaceBlueprint
(plus the EnvironmentSpec, SetupIntent, and Repository DNA). This is still a
PREPARATION phase.

Generating a provision plan never starts Docker, runs Docker Compose, executes
repository code, starts services or processes, deploys anything, creates cloud
resources, installs dependencies, modifies the repository, or writes secrets.
Every command/sequence is a PLAN, not a run. The only network use is the
existing read-only GitHub metadata used upstream. Full organization isolation.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError
from app.models.environment_spec import EnvironmentSpec
from app.models.repository import Repository
from app.models.setup_intent import SetupIntent
from app.models.workspace_blueprint import WorkspaceBlueprint
from app.models.workspace_provision_plan import WorkspaceProvisionPlan
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)

JS_RUNTIMES = {"Node.js"}
PY_RUNTIMES = {"CPython", "Python"}


class WorkspaceProvisioner:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    # -- queries ---------------------------------------------------------------

    def get_for_repository(
        self, repository_id: uuid.UUID, organization_id: uuid.UUID
    ) -> WorkspaceProvisionPlan:
        plan = self._fetch(repository_id, organization_id)
        if not plan:
            raise NotFoundError("Workspace provision plan not found")
        return plan

    def get_optional(
        self, repository_id: uuid.UUID, organization_id: uuid.UUID
    ) -> WorkspaceProvisionPlan | None:
        return self._fetch(repository_id, organization_id)

    def _fetch(
        self, repository_id: uuid.UUID, organization_id: uuid.UUID
    ) -> WorkspaceProvisionPlan | None:
        return self.db.scalar(
            select(WorkspaceProvisionPlan).where(
                WorkspaceProvisionPlan.repository_id == repository_id,
                WorkspaceProvisionPlan.organization_id == organization_id,
            )
        )

    # -- command ---------------------------------------------------------------

    def generate(
        self,
        *,
        repository_id: uuid.UUID,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
    ) -> WorkspaceProvisionPlan:
        repository = self._require_repository(repository_id, organization_id)
        blueprint = self.db.scalar(
            select(WorkspaceBlueprint).where(
                WorkspaceBlueprint.repository_id == repository_id,
                WorkspaceBlueprint.organization_id == organization_id,
            )
        )
        if blueprint is None:
            raise AppError("No workspace blueprint found. Generate the workspace blueprint first.")

        spec = self.db.scalar(
            select(EnvironmentSpec).where(
                EnvironmentSpec.repository_id == repository_id,
                EnvironmentSpec.organization_id == organization_id,
            )
        )
        setup_intent = self.db.scalar(
            select(SetupIntent).where(
                SetupIntent.repository_id == repository_id,
                SetupIntent.organization_id == organization_id,
            )
        )

        fields = self.build_plan(repository, blueprint, spec, setup_intent)

        plan = self.db.scalar(
            select(WorkspaceProvisionPlan).where(WorkspaceProvisionPlan.repository_id == repository.id)
        )
        if plan is None:
            plan = WorkspaceProvisionPlan(organization_id=organization_id, repository_id=repository.id)
            self.db.add(plan)
        for key, value in fields.items():
            setattr(plan, key, value)

        self.db.flush()
        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="workspace_provision_generated",
            target_type="repository",
            target_id=str(repository.id),
            metadata={"readiness_score": fields["readiness_score"]},
        )
        self.db.commit()
        self.db.refresh(plan)
        return plan

    # -- build -----------------------------------------------------------------

    def build_plan(
        self,
        repository: Repository,
        blueprint: WorkspaceBlueprint,
        spec: EnvironmentSpec | None,
        setup_intent: SetupIntent | None,
    ) -> dict:
        is_js = blueprint.runtime in JS_RUNTIMES
        is_py = blueprint.runtime in PY_RUNTIMES
        bp_startup = blueprint.startup_plan or {}
        resources = blueprint.workspace_resources or {}
        services = list(resources.get("services") or [])
        env_files = blueprint.environment_files or []
        env_names = self._env_names(env_files, spec)
        has_env_example = self._has_env_example(env_files, spec)
        docker_assets = blueprint.docker_assets or []
        has_dockerfile = self._asset_existing(docker_assets, "Dockerfile")
        has_compose = self._asset_existing(docker_assets, "docker-compose.yml")
        has_docker = has_dockerfile or has_compose

        install_seq = self._plan_steps(bp_startup.get("install_sequence"))
        build_seq = self._plan_steps(bp_startup.get("build_sequence"))
        start_seq = self._plan_steps(bp_startup.get("start_sequence"))
        health_seq = self._plan_steps(bp_startup.get("health_check_sequence"))

        workspace_directory = self._workspace_directory(repository)
        environment_preparation = self._environment_preparation(blueprint, env_names, has_env_example)
        app_ports = list(getattr(spec, "app_ports", None) or [])
        container_preparation = self._container_preparation(
            blueprint, docker_assets, services, has_dockerfile, has_compose, is_js, is_py, app_ports
        )
        dependency_plan = self._dependency_plan(install_seq, blueprint)
        startup_plan = self._startup_plan(install_seq, build_seq, start_seq, health_seq, services)
        validation, score = self._validation(
            blueprint, install_seq, start_seq, health_seq, services, has_env_example, has_docker
        )
        warnings = list(blueprint.warnings or [])
        recommendations = list(blueprint.recommendations or [])

        return {
            "language": blueprint.language,
            "runtime": blueprint.runtime,
            "runtime_version": blueprint.runtime_version,
            "package_manager": blueprint.package_manager,
            "framework": blueprint.framework,
            "workspace_directory": workspace_directory,
            "environment_preparation": environment_preparation,
            "container_preparation": container_preparation,
            "dependency_plan": dependency_plan,
            "startup_plan": startup_plan,
            "validation": validation,
            "readiness_score": score,
            "recommendations": recommendations,
            "warnings": warnings,
            "safety": {
                "read_only": True,
                "no_code_execution": True,
                "no_docker": True,
                "no_dependency_installation": True,
                "no_service_launch": True,
                "no_deployment": True,
                "no_cloud_resources": True,
                "no_repository_modification": True,
                "no_secret_exposure": True,
                "network": "existing GitHub metadata only",
                "org_isolated": True,
            },
        }

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _env_names(env_files: list, spec: EnvironmentSpec | None) -> list[str]:
        for f in env_files:
            if isinstance(f, dict) and f.get("name") == ".env.example" and f.get("variable_names"):
                return list(f["variable_names"])
        if spec and spec.env_vars:
            return [e.get("name") for e in spec.env_vars if isinstance(e, dict) and e.get("name")]
        return []

    @staticmethod
    def _has_env_example(env_files: list, spec: EnvironmentSpec | None) -> bool:
        for f in env_files:
            if isinstance(f, dict) and f.get("name") == ".env.example" and f.get("action") == "existing":
                return True
        if spec is not None:
            return not spec.missing_env_example
        return False

    @staticmethod
    def _asset_existing(assets: list, name: str) -> bool:
        return any(
            isinstance(a, dict) and a.get("name") == name and a.get("status") == "existing" for a in assets
        )

    @staticmethod
    def _plan_steps(steps) -> list[str]:
        """Return concrete planned commands, dropping 'No ... detected.' placeholders."""
        if not steps:
            return []
        return [s for s in steps if isinstance(s, str) and not s.lower().startswith("no ")]

    @staticmethod
    def _workspace_directory(repository: Repository) -> dict:
        root = f"/workspaces/{repository.name}"
        return {
            "workspace_root": root,
            "repository_location": f"{root}/repo",
            "config_directory": f"{root}/.codedna",
            "cache_directory": f"{root}/.cache",
            "logs_directory": f"{root}/logs",
            "temp_directory": f"{root}/tmp",
            "note": "Planned layout only. No directories are created.",
        }

    def _environment_preparation(
        self, blueprint: WorkspaceBlueprint, env_names: list[str], has_env_example: bool
    ) -> dict:
        runtime_version_files = [
            f.get("name")
            for f in (blueprint.environment_files or [])
            if isinstance(f, dict) and f.get("name") in {".nvmrc", ".python-version"}
        ]
        pm = blueprint.package_manager
        pm_config = None
        if pm in {"npm", "pnpm", "yarn"}:
            pm_config = ".npmrc"
        elif pm in {"pip", "poetry", "uv"}:
            pm_config = "pip.conf / pyproject.toml"
        return {
            "env_template": env_names,
            "generated_env_template": ".env (template; variable names only, no values)",
            "runtime_config": {
                "runtime": blueprint.runtime,
                "runtime_version": blueprint.runtime_version,
            },
            "runtime_version_files": runtime_version_files,
            "package_manager_config": {"manager": pm, "config_file": pm_config},
            "has_env_example": has_env_example,
            "note": "Secrets are never read or written. Variable names only.",
        }

    def _container_preparation(
        self,
        blueprint: WorkspaceBlueprint,
        docker_assets: list,
        services: list[str],
        has_dockerfile: bool,
        has_compose: bool,
        is_js: bool,
        is_py: bool,
        app_ports: list[int],
    ) -> dict:
        if is_py:
            base_image = f"python:{blueprint.runtime_version or '3.12'}-slim"
        elif is_js:
            base_image = f"node:{blueprint.runtime_version or '20'}-bookworm-slim"
        else:
            base_image = "to be determined"
        return {
            "docker_image_plan": {
                "status": "existing" if has_dockerfile else "proposed",
                "base_image": base_image,
                "note": "Image plan only. No image is built." ,
            },
            "docker_compose_plan": {
                "status": "existing" if has_compose else ("proposed" if services else "not_required"),
                "services": ["app", *services],
                "note": "Compose plan only. No containers are started.",
            },
            "dev_container_plan": {
                "status": "proposed" if (is_js or is_py) else "not_applicable",
                "file": ".devcontainer/devcontainer.json",
            },
            "network_plan": {
                "isolated": True,
                "exposed_ports": app_ports,
            },
            "volume_plan": {
                "volumes": list((blueprint.workspace_resources or {}).get("volumes", [])),
                "workspace_mount": "workspace:/workspaces (planned)",
            },
            "note": "No containers are created.",
        }

    @staticmethod
    def _dependency_plan(install_seq: list[str], blueprint: WorkspaceBlueprint) -> list[dict]:
        steps = []
        for cmd in install_seq:
            steps.append({"command": cmd, "status": "planned"})
        if not steps:
            steps.append(
                {
                    "command": "No install command detected.",
                    "status": "missing",
                }
            )
        return steps

    @staticmethod
    def _startup_plan(
        install_seq: list[str],
        build_seq: list[str],
        start_seq: list[str],
        health_seq: list[str],
        services: list[str],
    ) -> list[dict]:
        return [
            {
                "order": 1,
                "phase": "Prepare runtime",
                "actions": ["Select runtime version", "Apply runtime version files"],
            },
            {
                "order": 2,
                "phase": "Prepare dependencies",
                "actions": install_seq or ["No install command detected."],
            },
            {
                "order": 3,
                "phase": "Prepare services",
                "actions": [f"Provision {s}" for s in services] or ["No backing services required."],
            },
            {
                "order": 4,
                "phase": "Prepare application",
                "actions": (build_seq or ["No build step required."]) + (start_seq or ["No start command detected."]),
            },
            {
                "order": 5,
                "phase": "Verify health",
                "actions": health_seq or ["No health check detected."],
            },
            {"order": 6, "phase": "Ready", "actions": ["Workspace prepared (not launched)."]},
        ]

    @staticmethod
    def _validation(
        blueprint: WorkspaceBlueprint,
        install_seq: list[str],
        start_seq: list[str],
        health_seq: list[str],
        services: list[str],
        has_env_example: bool,
        has_docker: bool,
    ) -> tuple[list[dict], int]:
        runtime_ok = blueprint.runtime is not None
        commands_ok = bool(install_seq) and bool(start_seq)
        env_ok = has_env_example
        health_ok = bool(health_seq)
        checks = [
            {
                "label": "Runtime detected",
                "status": "ok" if runtime_ok else "warning",
                "detail": blueprint.runtime or "Runtime could not be determined.",
                "points": 20,
            },
            {
                "label": "Startup plan",
                "status": "ok" if commands_ok else "warning",
                "detail": "Install and start commands available." if commands_ok else "Missing install or start command.",
                "points": 20,
            },
            {
                "label": "Environment complete",
                "status": "ok" if env_ok else "warning",
                "detail": ".env.example present." if env_ok else "Missing .env.example.",
                "points": 20,
            },
            {
                "label": "Services identified",
                "status": "ok",
                "detail": ", ".join(services) if services else "No backing services required.",
                "points": 15,
            },
            {
                "label": "Docker configuration",
                "status": "ok" if has_docker else "warning",
                "detail": "Docker configuration present." if has_docker else "No Docker configuration; a plan is proposed.",
                "points": 15,
            },
            {
                "label": "Health check",
                "status": "ok" if health_ok else "warning",
                "detail": "Health check available." if health_ok else "No health check detected.",
                "points": 10,
            },
        ]
        score = sum(c["points"] for c in checks if c["status"] == "ok")
        return checks, score

    def _require_repository(
        self, repository_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Repository:
        repository = self.db.scalar(
            select(Repository).where(
                Repository.id == repository_id,
                Repository.organization_id == organization_id,
            )
        )
        if not repository:
            raise NotFoundError("Repository not found")
        return repository
