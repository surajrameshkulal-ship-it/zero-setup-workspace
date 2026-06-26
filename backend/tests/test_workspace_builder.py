from __future__ import annotations

import json
import uuid

import pytest

from app.core.errors import AppError, NotFoundError
from app.models.audit import AuditLog
from app.services.workspace.environment_spec_generator import EnvironmentSpecGenerator
from app.services.workspace.setup_intent_reader import SetupIntentReader
from app.services.workspace.workspace_builder import WorkspaceBuilder

REPO_BASE = "/api/v1/repositories"


def _pipeline(api_context, files: dict[str, str]):
    """Setup intent -> environment spec (the blueprint's input)."""
    SetupIntentReader(api_context.db).generate(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        files=files,
    )
    return EnvironmentSpecGenerator(api_context.db).generate(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )


def _blueprint_fields(api_context, files: dict[str, str]) -> dict:
    spec = _pipeline(api_context, files)
    setup = SetupIntentReader(api_context.db).get_optional(api_context.repository.id, api_context.organization.id)
    return WorkspaceBuilder(api_context.db).build_blueprint(api_context.repository, spec, setup, dna=None)


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


def test_node_workspace(api_context) -> None:
    bp = _blueprint_fields(api_context, NODE_FILES)
    assert bp["runtime"] == "Node.js"
    assert bp["framework"] == "Next.js"
    assert ".next" in bp["workspace_structure"]["generated_directories"]
    assert "__tests__" in bp["workspace_structure"]["test_directories"]
    # IDE assets proposed for JS
    assert any(a["name"] == ".vscode/extensions.json" for a in bp["ide_assets"])
    # startup plan contains the install + start commands as PLANS only
    assert "npm install" in bp["startup_plan"]["install_sequence"]
    assert any("npm run dev" in s or "npm start" in s for s in bp["startup_plan"]["start_sequence"])
    assert bp["safety"]["no_code_execution"] is True


def test_python_docker_workspace(api_context) -> None:
    bp = _blueprint_fields(api_context, PY_FILES)
    assert bp["runtime"] == "CPython"
    assert "__pycache__" in bp["workspace_structure"]["generated_directories"]
    # Existing Dockerfile/compose are marked existing (never overwritten)
    docker = {a["name"]: a["status"] for a in bp["docker_assets"]}
    assert docker["Dockerfile"] == "existing"
    assert docker["docker-compose.yml"] == "existing"
    # compose services appear in startup + resources
    assert any("docker compose up" in s for s in bp["startup_plan"]["install_sequence"])
    assert "PostgreSQL" in bp["workspace_resources"]["services"]
    assert any("postgresql" in v for v in bp["workspace_resources"]["volumes"])
    # high readiness: install/run/pm/test/docker/health/env all present
    assert bp["readiness_score"] >= 90


def test_proposed_docker_for_repo_without_docker(api_context) -> None:
    bp = _blueprint_fields(api_context, NODE_FILES)  # no Dockerfile
    docker = {a["name"]: a["status"] for a in bp["docker_assets"]}
    assert docker["Dockerfile"] == "proposed"  # proposed, never overwriting


def test_readme_only_low_readiness(api_context) -> None:
    bp = _blueprint_fields(api_context, {"README.md": "# project\n"})
    assert bp["readiness_score"] < 40
    assert "No test command detected." in bp["warnings"]
    assert "No Docker support detected." in bp["warnings"]
    assert bp["recommendations"]


def test_missing_env_example_warning_and_recommendation(api_context) -> None:
    bp = _blueprint_fields(api_context, {"requirements.txt": "flask\n", "README.md": "# x\n"})
    assert "Missing .env.example." in bp["warnings"]
    assert any(".env.example" in r for r in bp["recommendations"])
    # .env.example is marked to be generated
    env_actions = {f["name"]: f["action"] for f in bp["environment_files"]}
    assert env_actions[".env.example"] == "generate"


def test_env_vars_names_only(api_context) -> None:
    bp = _blueprint_fields(
        api_context, {".env.example": "API_TOKEN=should-not-store\nDEBUG=\n", "requirements.txt": "flask\n"}
    )
    env_file = next(f for f in bp["environment_files"] if f["name"] == ".env.example")
    assert "API_TOKEN" in env_file["variable_names"]
    assert "should-not-store" not in json.dumps(bp)


def test_generate_persists_and_audits(api_context) -> None:
    _pipeline(api_context, NODE_FILES)
    bp = WorkspaceBuilder(api_context.db).generate(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    assert bp.id is not None
    assert bp.readiness_score > 0
    assert "workspace_blueprint_generated" in {r.action for r in api_context.db.query(AuditLog).all()}


def test_idempotent_regeneration(api_context) -> None:
    _pipeline(api_context, NODE_FILES)
    builder = WorkspaceBuilder(api_context.db)
    first = builder.generate(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    second = builder.generate(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    assert first.id == second.id


def test_requires_environment_spec(api_context) -> None:
    with pytest.raises(AppError):
        WorkspaceBuilder(api_context.db).generate(
            repository_id=api_context.repository.id,
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
        )


def test_api_get_post_and_404(api_context) -> None:
    assert api_context.client.get(f"{REPO_BASE}/{api_context.repository.id}/workspace-blueprint").status_code == 404
    _pipeline(api_context, NODE_FILES)
    posted = api_context.client.post(f"{REPO_BASE}/{api_context.repository.id}/workspace-blueprint")
    assert posted.status_code == 200
    assert posted.json()["runtime"] == "Node.js"
    fetched = api_context.client.get(f"{REPO_BASE}/{api_context.repository.id}/workspace-blueprint")
    assert fetched.status_code == 200
    assert fetched.json()["repository_full_name"] == "acme/payments-api"


def test_org_isolation(api_context) -> None:
    assert api_context.client.get(f"{REPO_BASE}/{api_context.other_repository.id}/workspace-blueprint").status_code == 404
    assert api_context.client.post(f"{REPO_BASE}/{api_context.other_repository.id}/workspace-blueprint").status_code == 404
    with pytest.raises(NotFoundError):
        WorkspaceBuilder(api_context.db).generate(
            repository_id=api_context.other_repository.id,
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
        )
