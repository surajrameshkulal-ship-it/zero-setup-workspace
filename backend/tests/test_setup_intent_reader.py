from __future__ import annotations

import json
import uuid

import pytest

from app.core.errors import NotFoundError
from app.models.audit import AuditLog
from app.services.workspace.setup_intent_reader import SetupIntentReader

REPO_BASE = "/api/v1/repositories"


def _reader(api_context) -> SetupIntentReader:
    return SetupIntentReader(api_context.db)


def _build(api_context, files: dict[str, str]):
    return _reader(api_context).build_intent(api_context.repository, files, dna=None)


def test_node_project_inference() -> None:
    pass  # placeholder to keep import side-effects minimal


def test_infers_node_next_project(api_context) -> None:
    files = {
        "package.json": json.dumps(
            {
                "engines": {"node": ">=20"},
                "scripts": {"dev": "next dev", "build": "next build", "start": "next start", "lint": "eslint .", "test": "vitest"},
                "dependencies": {"next": "15.0.0", "react": "18", "stripe": "12"},
                "devDependencies": {"typescript": "5", "tailwindcss": "3"},
            }
        ),
        "package-lock.json": "{}",
        ".env.example": "NEXT_PUBLIC_API_URL=\nSTRIPE_KEY=secret-should-not-be-captured\n# comment\n",
    }
    intent = _build(api_context, files)
    assert "JavaScript" in intent["languages"]
    assert "TypeScript" in intent["languages"]
    assert "Next.js" in intent["frameworks"]
    assert "React" in intent["frameworks"]
    assert intent["package_manager"] == "npm"
    assert intent["runtime_version"] == "Node >=20"
    assert intent["install_command"] == "npm install"
    assert intent["dev_command"] == "npm run dev"
    assert intent["build_command"] == "npm run build"
    assert intent["prod_command"] == "npm start"
    assert intent["lint_command"] == "npm run lint"
    assert intent["test_command"] == "npm run test"
    assert "Stripe" in intent["external_services"]
    # env var NAMES only, never values
    assert set(intent["env_vars"]) == {"NEXT_PUBLIC_API_URL", "STRIPE_KEY"}
    assert "secret-should-not-be-captured" not in json.dumps(intent)
    assert intent["confidence_score"] > 0.5


def test_infers_python_fastapi_with_docker(api_context) -> None:
    files = {
        "pyproject.toml": '[project]\nname = "x"\nrequires-python = ">=3.12"\ndependencies = ["fastapi", "sqlalchemy", "psycopg", "redis", "celery"]\n',
        "requirements.txt": "fastapi\npsycopg\nredis\npytest\n",
        "Dockerfile": "FROM python:3.12-slim\nEXPOSE 8000\nCMD uvicorn app.main:app\n",
        "docker-compose.yml": "services:\n  db:\n    image: postgres:16\n    ports:\n      - '5432:5432'\n  cache:\n    image: redis:7\n",
        ".github/workflows/ci.yml": "name: ci\non: [push]\n",
        "README.md": "Health check at /health\n",
    }
    intent = _build(api_context, files)
    assert "Python" in intent["languages"]
    assert "FastAPI" in intent["frameworks"]
    assert intent["runtime_version"] == "Python >=3.12"
    assert intent["package_manager"] in ("pip", "poetry")
    assert intent["install_command"] == "pip install -e ."
    assert intent["test_command"] == "python -m pytest"
    assert "uvicorn" in (intent["dev_command"] or "")
    assert "PostgreSQL" in intent["databases"]
    assert "Redis" in intent["caches"]
    assert "Celery" in intent["queues"]
    assert intent["docker"]["present"] is True
    assert 8000 in intent["ports"]
    assert 5432 in intent["ports"]
    assert intent["cicd_provider"] == "GitHub Actions"
    assert intent["health_check_endpoint"] == "/health"


def test_makefile_and_procfile_fallbacks(api_context) -> None:
    files = {
        "requirements.txt": "flask\n",
        "Makefile": "install:\n\tpip install -r requirements.txt\ntest:\n\tpytest\nrun:\n\tflask run\n",
        "Procfile": "web: gunicorn app:app\n",
    }
    intent = _build(api_context, files)
    assert intent["test_command"] in ("python -m pytest", "make test")
    assert intent["prod_command"] in ("gunicorn app:app", "make run")  # both are valid detections
    assert intent["install_command"] is not None


def test_empty_files_low_confidence(api_context) -> None:
    intent = _build(api_context, {})
    assert intent["confidence_score"] == 0.0
    assert intent["languages"] == []
    assert intent["notes"]


def test_reuses_repository_dna(api_context) -> None:
    from types import SimpleNamespace

    dna = SimpleNamespace(languages=["Go"], frameworks=["Gin"], databases=["MySQL"], queues=[])
    intent = _reader(api_context).build_intent(api_context.repository, {"requirements.txt": "flask\n"}, dna)
    assert "Go" in intent["languages"]  # baseline from DNA
    assert "Python" in intent["languages"]  # refined from manifest
    assert "Gin" in intent["frameworks"]
    assert "MySQL" in intent["databases"]


def test_generate_persists_and_audits(api_context) -> None:
    files = {"package.json": json.dumps({"scripts": {"build": "vite build"}, "dependencies": {"vue": "3"}})}
    intent = _reader(api_context).generate(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        files=files,
    )
    assert intent.id is not None
    assert "Vue" in intent.frameworks
    actions = {r.action for r in api_context.db.query(AuditLog).all()}
    assert "setup_intent_generated" in actions


def test_generate_is_idempotent(api_context) -> None:
    files = {"package.json": json.dumps({"dependencies": {"react": "18"}})}
    reader = _reader(api_context)
    first = reader.generate(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        files=files,
    )
    second = reader.generate(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        files=files,
    )
    assert first.id == second.id


def test_api_get_after_generation_and_404(api_context) -> None:
    # 404 before generation.
    assert api_context.client.get(f"{REPO_BASE}/{api_context.repository.id}/setup-intent").status_code == 404
    # Generate via service (avoids needing live GitHub), then GET via API.
    _reader(api_context).generate(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        files={"package.json": json.dumps({"dependencies": {"express": "4"}})},
    )
    response = api_context.client.get(f"{REPO_BASE}/{api_context.repository.id}/setup-intent")
    assert response.status_code == 200
    body = response.json()
    assert "Express" in body["frameworks"]
    assert body["repository_full_name"] == "acme/payments-api"


class _FakeGitHub:
    def __init__(self, *, files: dict[str, str], token_error=False, repo_error=False) -> None:
        self._files = files
        self._token_error = token_error
        self._repo_error = repo_error

    def get_installation_token(self, installation_id):
        from app.core.errors import IntegrationError

        if self._token_error:
            raise IntegrationError("bad token")
        return "tok"

    def get_branch_sha(self, **kwargs):
        from app.core.errors import IntegrationError

        if self._repo_error:
            raise IntegrationError("repo 404")
        return "sha123"

    def get_file_content(self, *, token, owner, repo, path, ref):
        from app.core.errors import IntegrationError

        if path in self._files:
            return self._files[path]
        raise IntegrationError(f"GitHub API request failed with status 404 for {path}")

    def list_directory(self, **kwargs):
        return []


def _connected_repo(api_context):
    from app.models.github import GitHubInstallation

    inst = GitHubInstallation(
        organization_id=api_context.organization.id,
        installation_id=4242,
        account_login="acme-labs",
        account_type="Organization",
        permissions={},
    )
    api_context.db.add(inst)
    api_context.db.flush()
    api_context.repository.github_installation_id = inst.id
    api_context.db.commit()


def test_provider_tolerates_missing_package_json(api_context) -> None:
    from app.services.workspace.setup_intent_reader import GitHubManifestFileProvider

    _connected_repo(api_context)
    gh = _FakeGitHub(files={"README.md": "# project\nrun with flask\n"})  # package.json etc. 404
    provider = GitHubManifestFileProvider(api_context.db, integration=gh)
    files = provider(api_context.repository)
    assert "README.md" in files
    assert "package.json" not in files  # missing, not fatal


def test_generate_succeeds_with_only_readme(api_context) -> None:
    from app.services.workspace.setup_intent_reader import GitHubManifestFileProvider

    _connected_repo(api_context)
    gh = _FakeGitHub(files={"README.md": "# demo\n"})
    intent = _reader(api_context).generate(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        file_provider=GitHubManifestFileProvider(api_context.db, integration=gh),
    )
    assert intent.sources_analyzed == ["README.md"]
    assert any("not present" in n for n in intent.notes)


def test_generate_succeeds_with_multiple_missing_manifests(api_context) -> None:
    from app.services.workspace.setup_intent_reader import GitHubManifestFileProvider

    _connected_repo(api_context)
    gh = _FakeGitHub(files={"README.md": "# x\n", "Dockerfile": "FROM python:3.12\nEXPOSE 8000\n"})
    intent = _reader(api_context).generate(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        file_provider=GitHubManifestFileProvider(api_context.db, integration=gh),
    )
    assert intent.docker["present"] is True
    assert 8000 in intent.ports
    assert intent.confidence_score < 0.6  # partial confidence, but no error


def test_provider_fails_on_repo_inaccessible(api_context) -> None:
    from app.core.errors import IntegrationError
    from app.services.workspace.setup_intent_reader import GitHubManifestFileProvider

    _connected_repo(api_context)
    gh = _FakeGitHub(files={"README.md": "x"}, repo_error=True)
    with pytest.raises(IntegrationError) as exc:
        GitHubManifestFileProvider(api_context.db, integration=gh)(api_context.repository)
    assert "unable to access repository" in str(exc.value).lower()


def test_provider_fails_on_token_error(api_context) -> None:
    from app.core.errors import IntegrationError
    from app.services.workspace.setup_intent_reader import GitHubManifestFileProvider

    _connected_repo(api_context)
    gh = _FakeGitHub(files={"README.md": "x"}, token_error=True)
    with pytest.raises(IntegrationError):
        GitHubManifestFileProvider(api_context.db, integration=gh)(api_context.repository)


def test_org_isolation(api_context) -> None:
    # GET and POST for another org's repository are not found.
    assert api_context.client.get(f"{REPO_BASE}/{api_context.other_repository.id}/setup-intent").status_code == 404
    assert api_context.client.post(f"{REPO_BASE}/{api_context.other_repository.id}/setup-intent").status_code == 404
    with pytest.raises(NotFoundError):
        _reader(api_context).generate(
            repository_id=api_context.other_repository.id,
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
            files={},
        )
