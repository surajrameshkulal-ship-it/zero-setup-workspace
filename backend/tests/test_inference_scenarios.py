"""Phase 11 inference upgrade: full-pipeline scenarios with an evidence trail.

Each scenario runs Setup Intent -> Environment Spec -> Workspace Blueprint ->
Workspace Provision and asserts non-null runtime fields, a non-zero confidence
score, a non-zero readiness score, and a populated evidence list.
"""

from __future__ import annotations

import json

from app.services.workspace.environment_spec_generator import EnvironmentSpecGenerator
from app.services.workspace.setup_intent_reader import SetupIntentReader
from app.services.workspace.workspace_builder import WorkspaceBuilder
from app.services.workspace.workspace_provisioner import WorkspaceProvisioner


def _pipeline(api_context, files: dict[str, str], file_tree=None):
    org = api_context.organization.id
    repo = api_context.repository.id
    user = api_context.user.id
    intent = SetupIntentReader(api_context.db).generate(
        repository_id=repo, organization_id=org, actor_user_id=user, files=files, file_tree=file_tree
    )
    spec = EnvironmentSpecGenerator(api_context.db).generate(
        repository_id=repo, organization_id=org, actor_user_id=user
    )
    blueprint = WorkspaceBuilder(api_context.db).generate(
        repository_id=repo, organization_id=org, actor_user_id=user
    )
    provision = WorkspaceProvisioner(api_context.db).generate(
        repository_id=repo, organization_id=org, actor_user_id=user
    )
    return intent, spec, blueprint, provision


def _assert_healthy(spec, blueprint, provision) -> None:
    assert spec.primary_language is not None
    assert spec.runtime_name is not None
    assert spec.confidence_score > 0.0
    assert spec.evidence  # evidence explains the inference
    assert blueprint.readiness_score > 0
    assert provision.readiness_score > 0


def test_nextjs_repo_with_package_json(api_context) -> None:
    files = {
        "package.json": json.dumps(
            {
                "engines": {"node": ">=20"},
                "scripts": {"dev": "next dev", "build": "next build", "start": "next start", "test": "vitest", "lint": "eslint ."},
                "dependencies": {"next": "15", "react": "18"},
                "devDependencies": {"typescript": "5"},
            }
        ),
        "package-lock.json": "{}",
        ".env.example": "NEXT_PUBLIC_API_URL=\n",
        "README.md": "# app\nrun `npm run dev`\nhealth at /health\n",
    }
    intent, spec, blueprint, provision = _pipeline(api_context, files, file_tree=["package.json", "app/page.tsx"])
    _assert_healthy(spec, blueprint, provision)
    assert spec.primary_language in ("TypeScript", "JavaScript")
    assert spec.runtime_name == "Node.js"
    assert spec.framework == "Next.js"
    assert spec.package_manager == "npm"
    assert spec.build_command == "npm run build"
    assert {e["field"] for e in spec.evidence} >= {"primary_language", "framework", "runtime_name"}


def test_fastapi_repo_with_pyproject(api_context) -> None:
    files = {
        "pyproject.toml": '[tool.poetry]\nname = "api"\n[project]\nrequires-python = ">=3.12"\ndependencies = ["fastapi", "psycopg", "redis", "pytest"]\n',
        "README.md": "# api\nhealth at /health\n",
    }
    intent, spec, blueprint, provision = _pipeline(api_context, files, file_tree=["pyproject.toml", "app/main.py"])
    _assert_healthy(spec, blueprint, provision)
    assert spec.primary_language == "Python"
    assert spec.runtime_name == "CPython"
    assert spec.framework == "FastAPI"
    assert spec.package_manager in ("poetry", "pip")
    assert "PostgreSQL" in spec.databases
    assert spec.test_command == "python -m pytest"


def test_python_repo_requirements_only(api_context) -> None:
    files = {"requirements.txt": "flask\ngunicorn\n"}
    intent, spec, blueprint, provision = _pipeline(api_context, files, file_tree=["requirements.txt", "app.py"])
    _assert_healthy(spec, blueprint, provision)
    assert spec.primary_language == "Python"
    assert spec.runtime_name == "CPython"
    assert spec.framework == "Flask"
    assert spec.package_manager == "pip"
    assert spec.install_command == "pip install -r requirements.txt"


def test_dockerized_repo(api_context) -> None:
    files = {
        "Dockerfile": "FROM python:3.12-slim\nEXPOSE 8000\nRUN pip install -r requirements.txt\nCMD uvicorn app.main:app --host 0.0.0.0 --port 8000\n",
        "docker-compose.yml": "services:\n  backend:\n    build: .\n    ports: ['8000:8000']\n  db:\n    image: postgres:16\n    ports: ['5432:5432']\n  cache:\n    image: redis:7\n",
    }
    intent, spec, blueprint, provision = _pipeline(api_context, files, file_tree=["Dockerfile", "docker-compose.yml", "app/main.py"])
    _assert_healthy(spec, blueprint, provision)
    assert spec.primary_language == "Python"
    assert spec.runtime_name == "CPython"
    assert spec.runtime_version == "Python 3.12"
    assert "PostgreSQL" in spec.databases
    assert "Redis" in spec.caches
    assert 8000 in spec.app_ports
    assert 5432 in spec.service_ports
    assert spec.container_strategy in ("docker", "docker-compose", "hybrid")


def test_repo_with_no_manifests_only_extensions(api_context) -> None:
    # No manifest files at all; inference must come from the file tree/directories.
    tree = ["src/server.go", "internal/handler/handler.go", "cmd/api/main.go", "README.md"]
    intent, spec, blueprint, provision = _pipeline(api_context, {}, file_tree=tree)
    _assert_healthy(spec, blueprint, provision)
    assert spec.primary_language == "Go"
    assert spec.runtime_name == "Go"
    # Evidence cites file extensions as the source.
    assert any("extension" in e["source"] for e in spec.evidence)


def test_mixed_frontend_backend_monorepo(api_context) -> None:
    files = {
        "package.json": json.dumps(
            {"workspaces": ["frontend"], "scripts": {"dev": "turbo dev", "build": "turbo build"}, "dependencies": {"next": "15"}}
        ),
        "frontend/package.json": json.dumps({"dependencies": {"next": "15", "react": "18"}}),
        "requirements.txt": "fastapi\nuvicorn\npsycopg\n",
        "docker-compose.yml": "services:\n  frontend:\n    build: ./frontend\n  backend:\n    build: ./backend\n  db:\n    image: postgres:16\n",
        "README.md": "# monorepo\nNext.js frontend + FastAPI backend\n",
    }
    tree = ["package.json", "requirements.txt", "frontend/app/page.tsx", "backend/app/main.py"]
    intent, spec, blueprint, provision = _pipeline(api_context, files, file_tree=tree)
    _assert_healthy(spec, blueprint, provision)
    # Both stacks detected.
    assert "Python" in intent.languages
    assert "JavaScript" in intent.languages or "TypeScript" in intent.languages
    assert "FastAPI" in intent.frameworks
    assert "Next.js" in intent.frameworks
    assert "PostgreSQL" in spec.databases
    # A single primary language/framework is still chosen deterministically.
    assert spec.primary_language is not None
    assert spec.framework is not None
