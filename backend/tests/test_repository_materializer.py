from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.core.errors import AppError, NotFoundError
from app.models.audit import AuditLog
from app.services.workspace.repository_materializer import RepositoryMaterializer
from app.services.workspace.secure_workspace_manager import SecureWorkspaceManager


def _materializer(api_context, tmp_path) -> RepositoryMaterializer:
    mgr = SecureWorkspaceManager(db=api_context.db, base_dir=tmp_path / "ws")
    return RepositoryMaterializer(api_context.db, workspace_manager=mgr)


def _connect(api_context) -> None:
    # Mark the fixture repository as connected to a GitHub installation.
    api_context.repository.github_installation_id = uuid.uuid4()
    api_context.db.commit()


def _fake_source(files: dict[str, bytes]):
    def provider(repository, dest_path):
        base = Path(dest_path)
        for rel, content in files.items():
            target = base / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        return {"commit_sha": "abc1234"}

    return provider


def test_materialize_metadata_only_when_clone_unavailable(api_context, tmp_path) -> None:
    _connect(api_context)
    mat = _materializer(api_context, tmp_path)
    snapshot = mat.materialize(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    assert snapshot.materialized is False
    assert snapshot.files_indexed_count == 0
    assert "live clone is not available" in (snapshot.reason or "").lower()
    assert snapshot.full_name == "acme/payments-api"
    assert snapshot.target_branch.startswith("codedna/ai/")

    api_context.db.flush()
    actions = {row.action for row in api_context.db.query(AuditLog).all()}
    assert "repository_materialization_started" in actions
    assert "repository_materialization_skipped" in actions


def test_rejects_unconnected_repository(api_context, tmp_path) -> None:
    mat = _materializer(api_context, tmp_path)  # fixture repo has no installation
    with pytest.raises(AppError):
        mat.materialize(
            repository_id=api_context.repository.id,
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
        )


def test_rejects_unsafe_branch(api_context, tmp_path) -> None:
    _connect(api_context)
    mat = _materializer(api_context, tmp_path)
    with pytest.raises(AppError):
        mat.materialize(
            repository_id=api_context.repository.id,
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
            target_branch="main",
        )


def test_excludes_forbidden_files(api_context, tmp_path) -> None:
    _connect(api_context)
    mat = _materializer(api_context, tmp_path)
    provider = _fake_source(
        {
            "app/main.py": b"print('hi')",
            "frontend/index.ts": b"export const x = 1;",
            ".env": b"SECRET=top-secret",
            "config/credentials.json": b"{}",
            "keys/server.pem": b"-----BEGIN-----",
            "pyproject.toml": b"[project]",
        }
    )
    snapshot = mat.materialize(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        source_provider=provider,
    )
    assert snapshot.materialized is True
    assert snapshot.commit_sha == "abc1234"
    # Forbidden files excluded from index and removed from the workspace.
    excluded_blob = " ".join(snapshot.excluded_files)
    assert ".env" in excluded_blob
    assert "credentials" in excluded_blob
    assert "server.pem" in excluded_blob
    ws = Path(snapshot.workspace_path)
    assert not (ws / ".env").exists()
    assert not (ws / "keys/server.pem").exists()
    # Safe files indexed; languages + important files detected.
    assert (ws / "app/main.py").exists()
    assert "Python" in snapshot.language_hints
    assert "TypeScript" in snapshot.language_hints
    assert "pyproject.toml" in snapshot.important_files_found
    assert snapshot.files_indexed_count == 3  # main.py, index.ts, pyproject.toml


def test_does_not_write_outside_workspace(api_context, tmp_path) -> None:
    _connect(api_context)
    mat = _materializer(api_context, tmp_path)
    provider = _fake_source({"app/main.py": b"x"})
    snapshot = mat.materialize(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        source_provider=provider,
    )
    ws = Path(snapshot.workspace_path).resolve()
    base = mat.workspace_manager.base_dir.resolve()
    # Workspace is inside the base; the only child of base is this workspace.
    assert base in ws.parents
    children = list(base.iterdir())
    assert children == [ws]


def test_cleanup_works(api_context, tmp_path) -> None:
    _connect(api_context)
    mat = _materializer(api_context, tmp_path)
    snapshot = mat.materialize(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        source_provider=_fake_source({"a.py": b"1"}),
    )
    assert Path(snapshot.workspace_path).exists()
    assert mat.cleanup(snapshot) is True
    assert not Path(snapshot.workspace_path).exists()


def test_org_isolation(api_context, tmp_path) -> None:
    mat = _materializer(api_context, tmp_path)
    with pytest.raises(NotFoundError):
        mat.materialize(
            repository_id=api_context.other_repository.id,  # different org
            organization_id=api_context.organization.id,
            actor_user_id=api_context.user.id,
        )
