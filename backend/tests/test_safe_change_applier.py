from __future__ import annotations

from pathlib import Path

import pytest

from app.core.errors import AppError
from app.services.agent.safe_change_applier import SafeChangeApplier
from app.services.workspace.secure_workspace_manager import SecureWorkspaceManager


def _setup(tmp_path, initial: dict[str, str] | None = None):
    mgr = SecureWorkspaceManager(base_dir=tmp_path / "ws")
    handle = mgr.create_workspace(branch_name="codedna/ai/feature-x", base_branch="main")
    ws = Path(handle.path)
    for rel, content in (initial or {}).items():
        target = ws / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    applier = SafeChangeApplier(workspace_manager=mgr, handle=handle)
    return applier, handle, ws


def test_create_file(tmp_path) -> None:
    applier, _handle, ws = _setup(tmp_path)
    changes = [{"path": "src/new.py", "operations": [{"type": "create_file", "content": "print('hi')\n"}]}]
    result = applier.apply(changes, dry_run=False)
    assert (ws / "src/new.py").read_text() == "print('hi')\n"
    assert result.files_changed == ["src/new.py"]
    assert any(op["type"] == "create_file" for op in result.applied_operations)
    assert result.patch_preview.strip()


def test_replace_file(tmp_path) -> None:
    applier, _handle, ws = _setup(tmp_path, {"a.py": "old\n"})
    changes = [{"path": "a.py", "operations": [{"type": "replace_file", "content": "new\n"}]}]
    applier.apply(changes, dry_run=False)
    assert (ws / "a.py").read_text() == "new\n"


def test_insert_after(tmp_path) -> None:
    applier, _handle, ws = _setup(tmp_path, {"a.py": "line1\nMARKER\nline2\n"})
    changes = [{"path": "a.py", "operations": [{"type": "insert_after", "target": "MARKER", "content": "\nINSERTED"}]}]
    applier.apply(changes, dry_run=False)
    assert (ws / "a.py").read_text() == "line1\nMARKER\nINSERTED\nline2\n"


def test_insert_before(tmp_path) -> None:
    applier, _handle, ws = _setup(tmp_path, {"a.py": "line1\nMARKER\nline2\n"})
    changes = [{"path": "a.py", "operations": [{"type": "insert_before", "target": "MARKER", "content": "INSERTED\n"}]}]
    applier.apply(changes, dry_run=False)
    assert (ws / "a.py").read_text() == "line1\nINSERTED\nMARKER\nline2\n"


def test_replace_block(tmp_path) -> None:
    applier, _handle, ws = _setup(tmp_path, {"a.py": "before\nOLD_BLOCK\nafter\n"})
    changes = [{"path": "a.py", "operations": [{"type": "replace_block", "target": "OLD_BLOCK", "content": "NEW_BLOCK"}]}]
    applier.apply(changes, dry_run=False)
    assert (ws / "a.py").read_text() == "before\nNEW_BLOCK\nafter\n"


def test_delete_file(tmp_path) -> None:
    applier, _handle, ws = _setup(tmp_path, {"gone.py": "bye\n"})
    changes = [{"path": "gone.py", "operations": [{"type": "delete_file"}]}]
    result = applier.apply(changes, dry_run=False)
    assert not (ws / "gone.py").exists()
    assert "gone.py" in result.files_changed


def test_unsupported_operation_skipped(tmp_path) -> None:
    applier, _handle, ws = _setup(tmp_path, {"a.py": "x\n"})
    changes = [{"path": "a.py", "operations": [{"type": "frobnicate", "content": "?"}]}]
    result = applier.apply(changes, dry_run=False)
    assert any(op["reason"] == "unsupported operation" for op in result.skipped_operations)
    assert result.safety_warnings
    assert (ws / "a.py").read_text() == "x\n"  # unchanged


def test_rejects_forbidden_path(tmp_path) -> None:
    applier, _handle, ws = _setup(tmp_path)
    changes = [{"path": ".env", "operations": [{"type": "create_file", "content": "SECRET=1"}]}]
    with pytest.raises(AppError):
        applier.apply(changes, dry_run=False)
    assert not (ws / ".env").exists()


def test_rejects_traversal(tmp_path) -> None:
    applier, _handle, _ws = _setup(tmp_path)
    changes = [{"path": "../escape.py", "operations": [{"type": "create_file", "content": "x"}]}]
    with pytest.raises(AppError):
        applier.apply(changes, dry_run=False)


def test_dry_run_does_not_modify_files(tmp_path) -> None:
    applier, _handle, ws = _setup(tmp_path)
    changes = [{"path": "src/new.py", "operations": [{"type": "create_file", "content": "print('hi')\n"}]}]
    result = applier.apply(changes, dry_run=True)
    assert result.dry_run is True
    assert result.files_changed == ["src/new.py"]  # would change
    assert result.rollback_snapshot == {}
    assert not (ws / "src/new.py").exists()  # but nothing written
    assert result.patch_preview.strip()


def test_rollback_restores_modified_file(tmp_path) -> None:
    applier, _handle, ws = _setup(tmp_path, {"a.py": "original\n"})
    changes = [{"path": "a.py", "operations": [{"type": "replace_file", "content": "changed\n"}]}]
    result = applier.apply(changes, dry_run=False)
    assert (ws / "a.py").read_text() == "changed\n"
    applier.rollback(result.rollback_snapshot)
    assert (ws / "a.py").read_text() == "original\n"


def test_rollback_removes_created_file(tmp_path) -> None:
    applier, _handle, ws = _setup(tmp_path)
    changes = [{"path": "new.py", "operations": [{"type": "create_file", "content": "x\n"}]}]
    result = applier.apply(changes, dry_run=False)
    assert (ws / "new.py").exists()
    applier.rollback(result.rollback_snapshot)
    assert not (ws / "new.py").exists()


def test_max_files_limit_enforced(tmp_path) -> None:
    mgr = SecureWorkspaceManager(base_dir=tmp_path / "ws")
    handle = mgr.create_workspace(branch_name="codedna/ai/x", base_branch="main")
    applier = SafeChangeApplier(workspace_manager=mgr, handle=handle, max_files=1)
    changes = [
        {"path": "a.py", "operations": [{"type": "create_file", "content": "1"}]},
        {"path": "b.py", "operations": [{"type": "create_file", "content": "2"}]},
    ]
    with pytest.raises(AppError):
        applier.apply(changes, dry_run=True)


def test_max_diff_limit_enforced(tmp_path) -> None:
    mgr = SecureWorkspaceManager(base_dir=tmp_path / "ws")
    handle = mgr.create_workspace(branch_name="codedna/ai/x", base_branch="main")
    applier = SafeChangeApplier(workspace_manager=mgr, handle=handle, max_diff_bytes=10)
    changes = [{"path": "a.py", "operations": [{"type": "create_file", "content": "x" * 100}]}]
    with pytest.raises(AppError):
        applier.apply(changes, dry_run=True)


def test_protected_branch_mutation_blocked(tmp_path) -> None:
    mgr = SecureWorkspaceManager(base_dir=tmp_path / "ws")
    # Manually craft a handle on a protected branch (bypassing create_workspace guard).
    handle = mgr.create_workspace(branch_name="codedna/ai/x", base_branch="main")
    handle.branch_name = "main"
    applier = SafeChangeApplier(workspace_manager=mgr, handle=handle)
    changes = [{"path": "a.py", "operations": [{"type": "create_file", "content": "x"}]}]
    with pytest.raises(AppError):
        applier.apply(changes, dry_run=True)
