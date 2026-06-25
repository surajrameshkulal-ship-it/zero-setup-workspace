"""Secure Workspace Manager (Phase 10, Step 1).

Creates isolated, sandboxed temporary directories that future phases will use
to execute AI-generated code. This step deliberately does NOT generate code,
clone repositories for real, commit, push, or open PRs. It only:

  * creates a workspace under a safe temp base directory
  * validates branch names and reports whether a checkout would be safe
    (metadata only — nothing is actually cloned)
  * protects against path traversal / forbidden system paths
  * enforces a maximum workspace size
  * cleans workspaces up
  * emits structured logs and (optionally) audit records

Every destructive operation is constrained to the workspace base; the manager
refuses to touch anything outside it.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.services.audit_service import AuditService
from app.services.execution.github_workspace_manager import GitHubWorkspaceManager

logger = logging.getLogger(__name__)

# Absolute system locations a workspace may never live under or delete.
FORBIDDEN_PREFIXES = (
    "/etc",
    "/usr",
    "/bin",
    "/sbin",
    "/lib",
    "/lib64",
    "/var",
    "/root",
    "/boot",
    "/sys",
    "/proc",
    "/dev",
)

# Path segments (relative to a workspace) that are never allowed.
FORBIDDEN_SEGMENT_PATTERNS = (
    r"^\.env",
    r"^\.git$",
    r"secret",
    r"credential",
    r"\.pem$",
    r"\.key$",
    r"^id_rsa",
)

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_DEFAULT_BASE_NAME = "codedna_workspaces"


def _slug(value: str, *, max_length: int = 32) -> str:
    cleaned = _SLUG_RE.sub("-", (value or "").lower()).strip("-")
    return cleaned[:max_length].strip("-") or "ws"


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


_SYSTEM_TEMP_ROOT = Path(tempfile.gettempdir()).resolve()


def _is_forbidden_path(path: Path) -> bool:
    resolved = path.resolve()
    # The system temp directory is always safe, even on platforms where it lives
    # under an otherwise-sensitive prefix (e.g. macOS temp under /var/folders).
    if _is_relative_to(resolved, _SYSTEM_TEMP_ROOT):
        return False
    resolved_str = str(resolved)
    if resolved_str == os.path.sep:
        return True
    return any(resolved_str == p or resolved_str.startswith(p + os.path.sep) for p in FORBIDDEN_PREFIXES)


@dataclass
class WorkspaceHandle:
    workspace_id: str
    path: str
    branch_name: str | None
    base_branch: str | None
    max_bytes: int
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_metadata(self) -> dict:
        return {
            "workspace_id": self.workspace_id,
            "path": self.path,
            "branch_name": self.branch_name,
            "base_branch": self.base_branch,
            "max_bytes": self.max_bytes,
            "created_at": self.created_at.isoformat(),
        }


class SecureWorkspaceManager:
    def __init__(self, *, db: Session | None = None, base_dir: str | os.PathLike | None = None) -> None:
        self.db = db
        self.audit = AuditService(db) if db is not None else None
        self.github = GitHubWorkspaceManager()

        configured = base_dir or settings.workspace_root
        if configured:
            base = Path(configured).expanduser().resolve()
        else:
            base = Path(tempfile.gettempdir()).resolve() / _DEFAULT_BASE_NAME

        if _is_forbidden_path(base) or str(base) == os.path.sep:
            raise AppError(f"Refusing to use an unsafe workspace base directory: {base}")

        self.base_dir = base
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max(1, settings.workspace_max_size_mb) * 1024 * 1024

    # -- branch validation -----------------------------------------------------

    def validate_branch_name(self, branch_name: str, base_branch: str | None = None) -> bool:
        return self.github.is_branch_safe(branch_name, base_branch)

    # -- creation --------------------------------------------------------------

    def create_workspace(
        self,
        *,
        identifier: str = "ws",
        branch_name: str | None = None,
        base_branch: str | None = None,
        organization_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> WorkspaceHandle:
        if branch_name is not None and not self.validate_branch_name(branch_name, base_branch):
            self._audit_blocked(organization_id, actor_user_id, "unsafe_branch", {"branch_name": branch_name})
            raise AppError(
                "Refusing to create a workspace for an unsafe branch "
                "(must be an isolated 'codedna/ai/...' branch, not a protected branch)."
            )

        prefix = f"{_slug(identifier)}-"
        created = tempfile.mkdtemp(prefix=prefix, dir=str(self.base_dir))
        path = Path(created).resolve()

        # Defense in depth: the new dir must be inside the base.
        if not _is_relative_to(path, self.base_dir) or _is_forbidden_path(path):
            shutil.rmtree(path, ignore_errors=True)
            raise AppError("Created workspace path failed safety validation.")

        handle = WorkspaceHandle(
            workspace_id=uuid.uuid4().hex,
            path=str(path),
            branch_name=branch_name,
            base_branch=base_branch,
            max_bytes=self.max_bytes,
        )
        logger.info(
            "workspace_created",
            extra={
                "workspace_id": handle.workspace_id,
                "path": handle.path,
                "branch_name": branch_name,
                "max_bytes": self.max_bytes,
            },
        )
        self._audit(organization_id, actor_user_id, "workspace_created", handle.as_metadata())
        return handle

    # -- checkout metadata (no real clone) -------------------------------------

    def prepare_checkout(
        self,
        handle: WorkspaceHandle,
        *,
        repository,
        organization_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> dict:
        """Return metadata describing whether a checkout would be safe.

        This NEVER clones. It validates repository state and branch safety and
        reports the decision so a later, separately gated phase can act on it.
        """
        state = self.github.validate_repository_state(repository, branch_name=handle.branch_name)
        clone_allowed = bool(
            state["repository_linked"] and state["is_active"] and state["branch_safe"]
        )
        metadata = {
            "workspace_id": handle.workspace_id,
            "repository_full_name": getattr(repository, "full_name", None) if repository else None,
            "default_branch": state["default_branch"],
            "branch_name": handle.branch_name,
            "clone_allowed": clone_allowed,
            "issues": state["issues"],
            "note": "Checkout metadata only — nothing was cloned or written.",
        }
        logger.info(
            "workspace_checkout_prepared",
            extra={"workspace_id": handle.workspace_id, "clone_allowed": clone_allowed},
        )
        self._audit(organization_id, actor_user_id, "workspace_checkout_prepared", metadata)
        return metadata

    # -- path safety -----------------------------------------------------------

    def resolve_path(self, handle: WorkspaceHandle, relative_path: str) -> Path:
        """Resolve a path inside the workspace, rejecting traversal/forbidden paths."""
        if relative_path is None:
            raise AppError("A relative path is required.")
        raw = str(relative_path)
        if "\x00" in raw:
            raise AppError("Path contains a null byte.")
        if raw.startswith("/") or raw.startswith("~") or raw.startswith("\\"):
            raise AppError("Absolute paths are not allowed inside a workspace.")

        workspace = Path(handle.path).resolve()
        candidate = (workspace / raw).resolve()
        if candidate != workspace and not _is_relative_to(candidate, workspace):
            raise AppError("Path escapes the workspace boundary.")

        rel_parts = candidate.relative_to(workspace).parts if candidate != workspace else ()
        for segment in rel_parts:
            lowered = segment.lower()
            if any(re.search(pattern, lowered) for pattern in FORBIDDEN_SEGMENT_PATTERNS):
                raise AppError(f"Forbidden path segment: '{segment}'.")
        return candidate

    # -- size limits -----------------------------------------------------------

    def current_size_bytes(self, handle: WorkspaceHandle) -> int:
        workspace = Path(handle.path)
        total = 0
        for root, _dirs, files in os.walk(workspace):
            for name in files:
                fp = Path(root) / name
                try:
                    total += fp.stat().st_size
                except OSError:
                    continue
        return total

    def within_size_limit(self, handle: WorkspaceHandle) -> bool:
        return self.current_size_bytes(handle) <= handle.max_bytes

    def enforce_size_limit(
        self,
        handle: WorkspaceHandle,
        *,
        organization_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> int:
        size = self.current_size_bytes(handle)
        if size > handle.max_bytes:
            self._audit_blocked(
                organization_id,
                actor_user_id,
                "size_limit_exceeded",
                {"workspace_id": handle.workspace_id, "size_bytes": size, "max_bytes": handle.max_bytes},
            )
            raise AppError(
                f"Workspace exceeds the maximum size "
                f"({size} bytes > {handle.max_bytes} bytes)."
            )
        return size

    # -- cleanup ---------------------------------------------------------------

    def cleanup(
        self,
        handle: WorkspaceHandle,
        *,
        organization_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> bool:
        workspace = Path(handle.path).resolve()
        base = self.base_dir.resolve()

        if workspace == base:
            raise AppError("Refusing to delete the workspace base directory.")
        if not _is_relative_to(workspace, base):
            raise AppError("Refusing to delete a path outside the workspace base.")
        if _is_forbidden_path(workspace):
            raise AppError("Refusing to delete a forbidden system path.")

        existed = workspace.exists()
        if existed:
            shutil.rmtree(workspace, ignore_errors=True)
        logger.info("workspace_cleaned", extra={"workspace_id": handle.workspace_id, "existed": existed})
        self._audit(
            organization_id,
            actor_user_id,
            "workspace_cleaned",
            {"workspace_id": handle.workspace_id, "existed": existed},
        )
        return existed

    # -- audit helpers ---------------------------------------------------------

    def _audit(
        self,
        organization_id: uuid.UUID | None,
        actor_user_id: uuid.UUID | None,
        action: str,
        metadata: dict,
    ) -> None:
        if self.audit is None or organization_id is None:
            return
        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type="workspace",
            target_id=str(metadata.get("workspace_id") or ""),
            metadata=metadata,
        )
        # Audit rows are flushed/committed by the caller's unit of work.

    def _audit_blocked(
        self,
        organization_id: uuid.UUID | None,
        actor_user_id: uuid.UUID | None,
        reason: str,
        metadata: dict,
    ) -> None:
        logger.warning("workspace_blocked", extra={"reason": reason, **metadata})
        self._audit(organization_id, actor_user_id, "workspace_blocked", {"reason": reason, **metadata})
