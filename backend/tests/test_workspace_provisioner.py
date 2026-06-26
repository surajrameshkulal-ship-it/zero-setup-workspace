from __future__ import annotations

import json

import pytest

from app.core.errors import AppError, NotFoundError
from app.models.audit import AuditLog
from app.services.workspace.environment_spec_generator import EnvironmentSpecGenerator
from app.services.workspace.setup_intent_reader import SetupIntentReader
from app.services.workspace.workspace_builder import WorkspaceBuilder
from app.services.workspace.workspace_provisioner import WorkspaceProvisioner

REPO_BASE = "/api/v1/repositories"


def _build_blueprint(api_context, files: dict[str, str]):
    """setup intent -> env spec -> workspace blueprint (the provisioner's input)."""
    SetupIntentReader(api_context.db).generate(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        files=files,
    )
    EnvironmentSpecGenerator(api_context.db).generate(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    return WorkspaceBuilder(api_context.db).generate(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )


def _provision_fields(api_context, files: dict[str, str]) -> dict:
    blueprint = _build_blueprint(api_context, files)
    spec = EnvironmentSpecGenerator(api_context.db).get_optional(
        api_context.repository.id, api_context.organization.id
    )
    setup = SetupIntentReader(api_context.db).get_optional(
        api_context.repository.id, api_context.organization.id
    )
    return WorkspaceProvisioner(api_context.db).build_plan(
        api_context.repository, blueprint, spec, setup
    )


NODE_FILES = {
    "package.json": json.dumps(
        {
            "engines": {"node": ">=20"},
            "scripts": {"dev": "next dev", "build": "next build", "start": "next start", "test": "vitest", "lint": "eslint ."},
            "dependencies": {"next": "15", "react": "18"},
        }
    ),
    "package-lock.json": "{}",
    ".env.example": "NEXT_PUBLIC_API_URL=\n",
    "README.md": "# app\nhealth at /health\n",
}

PY_FILES = {
    "pyproject.toml": '[project]\nrequires-python = ">=3.12"\ndependencies = ["fastapi", "psycopg", "redis", "celery"]\n',
    "requirements.txt": "fastapi\npsycopg\nredis\npytest\n",
    "Dockerfile": "FROM python:3.12-slim\nEXPOSE 8000\n",
    "docker-compose.yml": "services:\n  db:\n    image: postgres:16\n    ports: ['5432:5432']\n  cache:\n    image: redis:7\n",
    ".env.example": "DATABASE_URL=\n",
    "README.md": "# api\nhealth at /health\n",
}


def test_node_provision(api_context) -> None:
    plan = _provision_fields(api_context, NODE_FILES)
    assert plan["runtime"] == "Node.js"
    # directory layout is planned, not created
    assert plan["workspace_directory"]["workspace_root"].endswith("payments-api")
    assert "no directories are created" in plan["workspace_directory"]["note"].lower()
    # dependency plan contains the install command as a PLAN
    assert any(s["command"] == "npm install" for s in plan["dependency_plan"])
    assert all(s["status"] in {"planned", "missing"} for s in plan["dependency_plan"])
    # startup plan is the ordered 6-phase sequence
    phases = [p["phase"] for p in plan["startup_plan"]]
    assert phases == [
        "Prepare runtime",
        "Prepare dependencies",
        "Prepare services",
        "Prepare application",
        "Verify health",
        "Ready",
    ]
    # safety: nothing is executed or launched
    assert plan["safety"]["no_code_execution"] is True
    assert plan["safety"]["no_docker"] is True
    assert plan["safety"]["no_deployment"] is True


def test_python_docker_provision(api_context) -> None:
    plan = _provision_fields(api_context, PY_FILES)
    assert plan["runtime"] == "CPython"
    # docker image plan proposes a python base image but builds nothing
    assert "python:" in plan["container_preparation"]["docker_image_plan"]["base_image"]
    assert plan["container_preparation"]["docker_image_plan"]["status"] == "existing"
    assert plan["container_preparation"]["docker_compose_plan"]["status"] == "existing"
    # services identified
    assert "PostgreSQL" in plan["container_preparation"]["docker_compose_plan"]["services"]
    services_check = next(c for c in plan["validation"] if c["label"] == "Services identified")
    assert "PostgreSQL" in services_check["detail"]
    # high readiness
    assert plan["readiness_score"] >= 90


def test_readme_only_low_readiness(api_context) -> None:
    plan = _provision_fields(api_context, {"README.md": "# project\n"})
    assert plan["readiness_score"] < 60
    labels = {c["label"]: c["status"] for c in plan["validation"]}
    assert labels["Startup plan"] == "warning"
    assert labels["Environment complete"] == "warning"


def test_missing_env_validation_warns(api_context) -> None:
    plan = _provision_fields(api_context, {"requirements.txt": "flask\n", "README.md": "# x\n"})
    env_check = next(c for c in plan["validation"] if c["label"] == "Environment complete")
    assert env_check["status"] == "warning"
    assert ".env.example" in env_check["detail"]


def test_missing_docker_proposes_plan(api_context) -> None:
    plan = _provision_fields(api_context, NODE_FILES)  # no Dockerfile/compose
    assert plan["container_preparation"]["docker_image_plan"]["status"] == "proposed"
    docker_check = next(c for c in plan["validation"] if c["label"] == "Docker configuration")
    assert docker_check["status"] == "warning"


def test_readiness_scoring_components(api_context) -> None:
    plan = _provision_fields(api_context, PY_FILES)
    by_label = {c["label"]: c for c in plan["validation"]}
    assert by_label["Runtime detected"]["status"] == "ok"
    assert by_label["Health check"]["status"] == "ok"
    # score equals the sum of points for ok checks
    expected = sum(c["points"] for c in plan["validation"] if c["status"] == "ok")
    assert plan["readiness_score"] == expected


def test_no_secrets_stored(api_context) -> None:
    plan = _provision_fields(
        api_context, {".env.example": "API_TOKEN=should-not-store\n", "requirements.txt": "flask\n"}
    )
    assert "API_TOKEN" in plan["environment_preparation"]["env_template"]
    assert "should-not-store" not in json.dumps(plan)


def test_generate_persists_and_audits(api_context) -> None:
    _build_blueprint(api_context, NODE_FILES)
    plan = WorkspaceProvisioner(api_context.db).generate(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    assert plan.id is not None
    assert plan.readiness_score > 0
    assert "workspace_provision_generated" in {r.action for r in api_context.db.query(AuditLog).all()}


def test_idempotent_regeneration(api_context) -> None:
    _build_blueprint(api_context, NODE_FILES)
    prov = WorkspaceProvisioner(api_context.db)
    first = prov.generate(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    second = prov.generate(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    assert first.id == second.id


def test_requires_workspace_blueprint(api_context) -> None:
    with pytest.raises(AppError):
        WorkspaceProvisioner(api_context.db).generate(
            repository_id=api_context.repository.id,
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
        )


def test_api_get_post_and_404(api_context) -> None:
    assert api_context.client.get(f"{REPO_BASE}/{api_context.repository.id}/workspace-provision").status_code == 404
    _build_blueprint(api_context, NODE_FILES)
    posted = api_context.client.post(f"{REPO_BASE}/{api_context.repository.id}/workspace-provision")
    assert posted.status_code == 200
    assert posted.json()["runtime"] == "Node.js"
    fetched = api_context.client.get(f"{REPO_BASE}/{api_context.repository.id}/workspace-provision")
    assert fetched.status_code == 200
    assert fetched.json()["repository_full_name"] == "acme/payments-api"


def test_org_isolation(api_context) -> None:
    assert api_context.client.get(f"{REPO_BASE}/{api_context.other_repository.id}/workspace-provision").status_code == 404
    assert api_context.client.post(f"{REPO_BASE}/{api_context.other_repository.id}/workspace-provision").status_code == 404
    with pytest.raises(NotFoundError):
        WorkspaceProvisioner(api_context.db).generate(
            repository_id=api_context.other_repository.id,
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
        )
