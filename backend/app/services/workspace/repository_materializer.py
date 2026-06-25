"""Repository Materializer (Phase 10, Step 2).

Safely prepares a connected repository's source inside an isolated workspace
created by :class:`SecureWorkspaceManager`, then returns a snapshot of metadata.

This step does NOT generate code, commit, push, open PRs, or deploy. It only:

  * validates the repository is connected and the target branch is safe
  * (optionally) materializes a READ-ONLY copy of the source via an injected
    source provider / token service; if none is available it returns clear
    metadata explaining why
  * redacts secrets/.env/private keys, protects .git, and never indexes them
  * enforces the maximum repository size
  * never writes outside the workspace
  * emits audit events

The actual clone mechanism is pluggable (a `source_provider` callable). No live
clone is wired in this step, so by default the materializer returns
metadata-only snapshots.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError
from app.models.repository import Repository
from app.services.audit_service import AuditService
from app.services.workspace.secure_workspace_manager import (
    SecureWorkspaceManager,
    WorkspaceHandle,
)

logger = logging.getLogger(__name__)

# A source provider writes a read-only copy of the repository into `dest_path`
# and may return metadata such as {"commit_sha": "..."}.
SourceProvider = Callable[[Repository, str], dict | None]

# Files that must never be materialized/indexed (redacted if a provider wrote them).
FORBIDDEN_FILE_PATTERNS = (
    r"(^|/)\.env",
    r"secret",
    r"credential",
    r"\.pem$",
    r"\.key$",
    r"(^|/)id_rsa",
    r"\.p12$",
    r"\.pfx$",
)

IMPORTANT_FILES = {
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "pipfile",
    "go.mod",
    "cargo.toml",
    "pom.xml",
    "build.gradle",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "next.config.mjs",
    "next.config.js",
    "tsconfig.json",
    "readme.md",
    "makefile",
}

EXT_LANGUAGE = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".rb": "Ruby",
    ".php": "PHP",
    ".sql": "SQL",
    ".sh": "Shell",
}


def _is_forbidden_file(rel_path: str) -> bool:
    lowered = rel_path.lower()
    return any(re.search(pattern, lowered) for pattern in FORBIDDEN_FILE_PATTERNS)


@dataclass
class RepositorySnapshot:
    repository_id: str
    full_name: str
    default_branch: str | None
    target_branch: str | None
    commit_sha: str | None
    workspace_path: str | None
    materialized_at: datetime
    files_indexed_count: int
    important_files_found: list[str]
    language_hints: list[str]
    materialized: bool
    reason: str | None = None
    excluded_files: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "repository_id": self.repository_id,
            "full_name": self.full_name,
            "default_branch": self.default_branch,
            "target_branch": self.target_branch,
            "commit_sha": self.commit_sha,
            "workspace_path": self.workspace_path,
            "materialized_at": self.materialized_at.isoformat(),
            "files_indexed_count": self.files_indexed_count,
            "important_files_found": self.important_files_found,
            "language_hints": self.language_hints,
            "materialized": self.materialized,
            "reason": self.reason,
            "excluded_files": self.excluded_files,
        }


class RepositoryMaterializer:
    def __init__(
        self,
        db: Session,
        *,
        workspace_manager: SecureWorkspaceManager | None = None,
    ) -> None:
        self.db = db
        self.audit = AuditService(db)
        self.workspace_manager = workspace_manager or SecureWorkspaceManager(db=db)
        self._last_handle: WorkspaceHandle | None = None

    # -- command ---------------------------------------------------------------

    def materialize(
        self,
        *,
        repository_id: uuid.UUID,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        target_branch: str | None = None,
        source_provider: SourceProvider | None = None,
    ) -> RepositorySnapshot:
        repository = self._require_repository(repository_id, organization_id)
        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="repository_materialization_started",
            target_type="repository",
            target_id=str(repository.id),
            metadata={"full_name": repository.full_name},
        )

        try:
            default_branch = repository.default_branch or "main"
            effective_target = target_branch or f"codedna/ai/materialize-{str(repository.id)[:8]}"

            # Never check out a protected branch for modification.
            if not self.workspace_manager.validate_branch_name(effective_target, default_branch):
                self._audit(
                    organization_id, actor_user_id, "repository_materialization_failed",
                    repository, {"reason": "unsafe_target_branch", "target_branch": effective_target},
                )
                raise AppError(
                    "Refusing to materialize: target branch must be an isolated "
                    "'codedna/ai/...' branch, not a protected branch."
                )

            # Repository must be connected to a GitHub installation.
            if repository.github_installation_id is None or not repository.is_active:
                self._audit(
                    organization_id, actor_user_id, "repository_materialization_failed",
                    repository, {"reason": "repository_not_connected"},
                )
                raise AppError("Repository is not connected to an active GitHub installation.")

            handle = self.workspace_manager.create_workspace(
                identifier=repository.name,
                branch_name=effective_target,
                base_branch=default_branch,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
            )
            self._last_handle = handle

            clone_available = source_provider is not None
            if not clone_available:
                snapshot = self._metadata_only_snapshot(
                    repository,
                    default_branch=default_branch,
                    target_branch=effective_target,
                    workspace_path=handle.path,
                    reason=(
                        "Live clone is not available: no source provider/GitHub token "
                        "service is configured. Returned metadata only; nothing was cloned."
                    ),
                )
                self._audit(
                    organization_id, actor_user_id, "repository_materialization_skipped",
                    repository, {"reason": "clone_unavailable", "workspace_path": handle.path},
                )
                return snapshot

            # Materialize a READ-ONLY copy via the provider, then index safely.
            provider_meta = source_provider(repository, handle.path) or {}
            excluded = self._redact_forbidden(handle)
            self.workspace_manager.enforce_size_limit(
                handle, organization_id=organization_id, actor_user_id=actor_user_id
            )
            indexed, important, languages = self._index_workspace(handle)

            snapshot = RepositorySnapshot(
                repository_id=str(repository.id),
                full_name=repository.full_name,
                default_branch=default_branch,
                target_branch=effective_target,
                commit_sha=provider_meta.get("commit_sha"),
                workspace_path=handle.path,
                materialized_at=datetime.now(timezone.utc),
                files_indexed_count=indexed,
                important_files_found=important,
                language_hints=languages,
                materialized=True,
                reason=None,
                excluded_files=excluded,
            )
            self._audit(
                organization_id, actor_user_id, "repository_materialization_completed",
                repository,
                {
                    "workspace_path": handle.path,
                    "files_indexed_count": indexed,
                    "excluded_count": len(excluded),
                    "commit_sha": snapshot.commit_sha,
                },
            )
            return snapshot
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("repository_materialization_failed", extra={"error": str(exc)[:500]})
            self._audit(
                organization_id, actor_user_id, "repository_materialization_failed",
                repository, {"reason": str(exc)[:300]},
            )
            raise

    def cleanup(
        self,
        snapshot: RepositorySnapshot,
        *,
        organization_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> bool:
        if not snapshot.workspace_path:
            return False
        handle = WorkspaceHandle(
            workspace_id="materialized",
            path=snapshot.workspace_path,
            branch_name=snapshot.target_branch,
            base_branch=snapshot.default_branch,
            max_bytes=self.workspace_manager.max_bytes,
        )
        return self.workspace_manager.cleanup(
            handle, organization_id=organization_id, actor_user_id=actor_user_id
        )

    # -- helpers ---------------------------------------------------------------

    def _metadata_only_snapshot(
        self,
        repository: Repository,
        *,
        default_branch: str,
        target_branch: str,
        workspace_path: str | None,
        reason: str,
    ) -> RepositorySnapshot:
        return RepositorySnapshot(
            repository_id=str(repository.id),
            full_name=repository.full_name,
            default_branch=default_branch,
            target_branch=target_branch,
            commit_sha=None,
            workspace_path=workspace_path,
            materialized_at=datetime.now(timezone.utc),
            files_indexed_count=0,
            important_files_found=[],
            language_hints=[],
            materialized=False,
            reason=reason,
            excluded_files=[],
        )

    def _redact_forbidden(self, handle: WorkspaceHandle) -> list[str]:
        """Remove secret/.env/key files from the workspace. .git is left intact but skipped."""
        workspace = Path(handle.path)
        excluded: list[str] = []
        for root, dirs, files in os.walk(workspace, topdown=True):
            if ".git" in dirs:
                dirs.remove(".git")  # protect .git: never traverse or modify
            for name in files:
                abs_path = Path(root) / name
                rel = str(abs_path.relative_to(workspace))
                if _is_forbidden_file(rel):
                    try:
                        abs_path.unlink()
                    except OSError:
                        pass
                    excluded.append(rel)
        return excluded

    def _index_workspace(self, handle: WorkspaceHandle) -> tuple[int, list[str], list[str]]:
        workspace = Path(handle.path)
        count = 0
        important: set[str] = set()
        languages: set[str] = set()
        for root, dirs, files in os.walk(workspace, topdown=True):
            if ".git" in dirs:
                dirs.remove(".git")  # protected, not indexed
            for name in files:
                rel = str((Path(root) / name).relative_to(workspace))
                if _is_forbidden_file(rel):
                    continue
                count += 1
                base = name.lower()
                if base in IMPORTANT_FILES:
                    important.add(rel)
                ext = os.path.splitext(base)[1]
                if ext in EXT_LANGUAGE:
                    languages.add(EXT_LANGUAGE[ext])
        return count, sorted(important), sorted(languages)

    def _require_repository(self, repository_id: uuid.UUID, organization_id: uuid.UUID) -> Repository:
        repository = self.db.scalar(
            select(Repository).where(
                Repository.id == repository_id,
                Repository.organization_id == organization_id,
            )
        )
        if not repository:
            raise NotFoundError("Repository not found")
        return repository

    def _audit(
        self,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        action: str,
        repository: Repository,
        metadata: dict,
    ) -> None:
        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type="repository",
            target_id=str(repository.id),
            metadata=metadata,
        )
