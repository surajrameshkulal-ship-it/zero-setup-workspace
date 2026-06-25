from __future__ import annotations

from pathlib import Path

import pytest

from app.core.errors import AppError
from app.models.audit import AuditLog
from app.services.workspace.secure_workspace_manager import (
    SecureWorkspaceManager,
    WorkspaceHandle,
)


def _manager(tmp_path: Path, **kwargs) -> SecureWorkspaceManager:
    return SecureWorkspaceManager(base_dir=tmp_path / "workspaces", **kwargs)


def test_create_workspace_under_base(tmp_path) -> None:
    mgr = _manager(tmp_path)
    handle = mgr.create_workspace(identifier="req-123")
    ws = Path(handle.path)
    assert ws.exists() and ws.is_dir()
    assert mgr.base_dir in ws.resolve().parents
    assert handle.workspace_id
    assert handle.max_bytes > 0


def test_create_workspace_rejects_unsafe_branch(tmp_path) -> None:
    mgr = _manager(tmp_path)
    with pytest.raises(AppError):
        mgr.create_workspace(branch_name="main", base_branch="main")
    with pytest.raises(AppError):
        mgr.create_workspace(branch_name="feature/x")  # wrong prefix


def test_create_workspace_accepts_safe_branch(tmp_path) -> None:
    mgr = _manager(tmp_path)
    handle = mgr.create_workspace(branch_name="codedna/ai/bug-abc-fix", base_branch="main")
    assert handle.branch_name == "codedna/ai/bug-abc-fix"
    assert Path(handle.path).exists()


def test_branch_name_validation(tmp_path) -> None:
    mgr = _manager(tmp_path)
    assert mgr.validate_branch_name("codedna/ai/feature-x", "main") is True
    assert mgr.validate_branch_name("main", "main") is False
    assert mgr.validate_branch_name("develop", "main") is False


def test_resolve_path_allows_safe_relative(tmp_path) -> None:
    mgr = _manager(tmp_path)
    handle = mgr.create_workspace()
    resolved = mgr.resolve_path(handle, "src/module.py")
    assert mgr.base_dir in resolved.resolve().parents
    assert resolved.name == "module.py"


def test_resolve_path_blocks_traversal_and_absolute(tmp_path) -> None:
    mgr = _manager(tmp_path)
    handle = mgr.create_workspace()
    for bad in ["../escape.py", "../../etc/passwd", "/etc/passwd", "~/secret"]:
        with pytest.raises(AppError):
            mgr.resolve_path(handle, bad)


def test_resolve_path_blocks_forbidden_segments(tmp_path) -> None:
    mgr = _manager(tmp_path)
    handle = mgr.create_workspace()
    for bad in [".env", "config/.env.local", ".git", "deploy/secrets.yaml", "keys/server.pem"]:
        with pytest.raises(AppError):
            mgr.resolve_path(handle, bad)


def test_size_limit_enforced(tmp_path) -> None:
    mgr = _manager(tmp_path)
    handle = mgr.create_workspace()
    handle.max_bytes = 100  # shrink limit for the test

    # Under limit.
    (Path(handle.path) / "small.txt").write_bytes(b"x" * 50)
    assert mgr.within_size_limit(handle) is True
    assert mgr.enforce_size_limit(handle) == 50

    # Over limit.
    (Path(handle.path) / "big.txt").write_bytes(b"y" * 200)
    assert mgr.within_size_limit(handle) is False
    with pytest.raises(AppError):
        mgr.enforce_size_limit(handle)


def test_cleanup_removes_workspace(tmp_path) -> None:
    mgr = _manager(tmp_path)
    handle = mgr.create_workspace()
    assert Path(handle.path).exists()
    assert mgr.cleanup(handle) is True
    assert not Path(handle.path).exists()


def test_cleanup_refuses_outside_base(tmp_path) -> None:
    mgr = _manager(tmp_path)
    rogue = WorkspaceHandle(
        workspace_id="x",
        path="/etc",
        branch_name=None,
        base_branch=None,
        max_bytes=1024,
    )
    with pytest.raises(AppError):
        mgr.cleanup(rogue)


def test_cleanup_refuses_base_itself(tmp_path) -> None:
    mgr = _manager(tmp_path)
    rogue = WorkspaceHandle(
        workspace_id="x",
        path=str(mgr.base_dir),
        branch_name=None,
        base_branch=None,
        max_bytes=1024,
    )
    with pytest.raises(AppError):
        mgr.cleanup(rogue)


def test_unsafe_base_dir_rejected(tmp_path) -> None:
    with pytest.raises(AppError):
        SecureWorkspaceManager(base_dir="/etc")


def test_prepare_checkout_metadata_only(api_context, tmp_path) -> None:
    mgr = _manager(tmp_path)
    handle = mgr.create_workspace(branch_name="codedna/ai/bug-abc-x", base_branch="main")
    meta = mgr.prepare_checkout(handle, repository=api_context.repository)
    # Fixture repo is not linked to a GitHub installation -> not clone-allowed.
    assert meta["clone_allowed"] is False
    assert meta["repository_full_name"] == "acme/payments-api"
    assert "metadata only" in meta["note"].lower()


def test_audit_logging_with_db(api_context, tmp_path) -> None:
    mgr = SecureWorkspaceManager(db=api_context.db, base_dir=tmp_path / "ws")
    handle = mgr.create_workspace(
        identifier="req",
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    mgr.cleanup(
        handle,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    api_context.db.flush()  # manager defers commit to the caller's unit of work
    actions = {row.action for row in api_context.db.query(AuditLog).all()}
    assert "workspace_created" in actions
    assert "workspace_cleaned" in actions
