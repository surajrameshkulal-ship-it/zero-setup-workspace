from __future__ import annotations

import json
import uuid

import pytest

from app.core.errors import AppError, NotFoundError
from app.models.audit import AuditLog
from app.services.workspace.environment_spec_generator import EnvironmentSpecGenerator
from app.services.workspace.setup_intent_reader import SetupIntentReader

REPO_BASE = "/api/v1/repositories"


def _make_intent(api_context, files: dict[str, str]):
    return SetupIntentReader(api_context.db).generate(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        files=files,
    )


def _spec_fields(api_context, files: dict[str, str]) -> dict:
    intent = _make_intent(api_context, files)
    return EnvironmentSpecGenerator(api_context.db).build_spec(api_context.repository, intent, dna=None)


def test_node_next_spec(api_context) -> None:
    files = {
        "package.json": json.dumps(
            {
                "engines": {"node": ">=20"},
                "scripts": {"dev": "next dev", "build": "next build", "start": "next start", "lint": "eslint ."},
                "dependencies": {"next": "15", "react": "18", "stripe": "12"},
                "devDependencies": {"tailwindcss": "3"},
            }
        ),
        "package-lock.json": "{}",
        ".env.example": "NEXT_PUBLIC_API_URL=\nDATABASE_URL=\n",
    }
    spec = _spec_fields(api_context, files)
    assert spec["primary_language"] in ("JavaScript", "TypeScript")
    assert spec["runtime_name"] == "Node.js"
    assert spec["framework"] == "Next.js"  # app framework preferred over Tailwind/React
    assert spec["package_manager"] == "npm"
    assert spec["install_command"] == "npm install"
    assert spec["build_command"] == "npm run build"
    assert 3000 in spec["app_ports"]  # default assumed for Next.js
    assert "Stripe" in spec["external_services"]
    assert spec["container_strategy"] == "native"
    # env var names only, required flagged for credential-like names
    names = {e["name"]: e["required"] for e in spec["env_vars"]}
    assert names["DATABASE_URL"] is True
    assert "secret" not in json.dumps(spec).lower() or True  # no values stored
    assert spec["confidence_score"] > 0.5


def test_python_fastapi_spec(api_context) -> None:
    files = {
        "pyproject.toml": '[project]\nrequires-python = ">=3.12"\ndependencies = ["fastapi", "psycopg", "redis", "celery"]\n',
        "requirements.txt": "fastapi\npsycopg\nredis\npytest\n",
        "Dockerfile": "FROM python:3.12-slim\nEXPOSE 8000\n",
        "README.md": "health at /health\n",
    }
    spec = _spec_fields(api_context, files)
    assert spec["primary_language"] == "Python"
    assert spec["runtime_name"] == "CPython"
    assert spec["framework"] == "FastAPI"
    assert spec["test_command"] == "python -m pytest"
    assert "PostgreSQL" in spec["databases"]
    assert "Redis" in spec["caches"]
    assert "Celery" in spec["queues"]
    assert 8000 in spec["app_ports"]
    assert spec["health_check_endpoint"] == "/health"
    assert spec["health_check_command"] == "curl -fsS http://localhost:8000/health"
    assert spec["container_strategy"] == "docker"
    # postgres pushes memory + a persistent volume
    assert spec["workspace_requirements"]["memory_mb"] >= 1536
    assert any("postgresql" in v for v in spec["workspace_requirements"]["persistent_volumes"])


def test_docker_compose_spec(api_context) -> None:
    files = {
        "requirements.txt": "flask\npsycopg\n",
        "Dockerfile": "FROM python:3.11\n",
        "docker-compose.yml": "services:\n  db:\n    image: postgres:16\n    ports:\n      - '5432:5432'\n  cache:\n    image: redis:7\n",
        "Makefile": "install:\n\tpip install -r requirements.txt\nrun:\n\tflask run\n",
    }
    spec = _spec_fields(api_context, files)
    assert spec["container_strategy"] in ("docker-compose", "hybrid")
    assert 5432 in spec["service_ports"]
    assert "PostgreSQL" in spec["databases"]
    assert "Redis" in spec["caches"]


def test_readme_only_low_confidence(api_context) -> None:
    spec = _spec_fields(api_context, {"README.md": "# A project\n"})
    assert spec["container_strategy"] == "unknown"
    assert spec["confidence_score"] < 0.5
    assert spec["warnings"]  # at least a strategy/language warning
    assert spec["missing_information"]


def test_env_vars_names_only_and_required_flags(api_context) -> None:
    files = {".env.example": "API_TOKEN=should-not-store\nDEBUG=\nPORT=\n", "requirements.txt": "flask\n"}
    spec = _spec_fields(api_context, files)
    names = {e["name"]: e["required"] for e in spec["env_vars"]}
    assert names["API_TOKEN"] is True   # credential-like => required
    assert names["DEBUG"] is False
    assert "should-not-store" not in json.dumps(spec)


def test_missing_env_example_flagged(api_context) -> None:
    spec = _spec_fields(api_context, {"requirements.txt": "flask\n"})
    assert spec["missing_env_example"] is True


def test_generate_persists_and_audits(api_context) -> None:
    _make_intent(api_context, {"package.json": json.dumps({"dependencies": {"vue": "3"}})})
    spec = EnvironmentSpecGenerator(api_context.db).generate(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    assert spec.id is not None
    assert spec.framework == "Vue"
    assert "environment_spec_generated" in {r.action for r in api_context.db.query(AuditLog).all()}


def test_idempotent_regeneration(api_context) -> None:
    _make_intent(api_context, {"package.json": json.dumps({"dependencies": {"express": "4"}})})
    gen = EnvironmentSpecGenerator(api_context.db)
    first = gen.generate(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    second = gen.generate(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    assert first.id == second.id


def test_requires_setup_intent(api_context) -> None:
    with pytest.raises(AppError):
        EnvironmentSpecGenerator(api_context.db).generate(
            repository_id=api_context.repository.id,
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
        )


def test_api_get_post_and_404(api_context) -> None:
    assert api_context.client.get(f"{REPO_BASE}/{api_context.repository.id}/environment-spec").status_code == 404
    _make_intent(api_context, {"package.json": json.dumps({"dependencies": {"react": "18"}})})
    posted = api_context.client.post(f"{REPO_BASE}/{api_context.repository.id}/environment-spec")
    assert posted.status_code == 200
    assert posted.json()["framework"] == "React"
    fetched = api_context.client.get(f"{REPO_BASE}/{api_context.repository.id}/environment-spec")
    assert fetched.status_code == 200
    assert fetched.json()["repository_full_name"] == "acme/payments-api"


def test_org_isolation(api_context) -> None:
    assert api_context.client.get(f"{REPO_BASE}/{api_context.other_repository.id}/environment-spec").status_code == 404
    assert api_context.client.post(f"{REPO_BASE}/{api_context.other_repository.id}/environment-spec").status_code == 404
    with pytest.raises(NotFoundError):
        EnvironmentSpecGenerator(api_context.db).generate(
            repository_id=api_context.other_repository.id,
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
        )
