from __future__ import annotations

import re
import uuid

from app.models.engineering_request import EngineeringRequest
from app.models.repository import Repository

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Branch names the agent must never target.
PROTECTED_BRANCHES = {"main", "master", "develop", "release", "production"}


def _slugify(value: str, *, max_length: int = 40) -> str:
    slug = _SLUG_RE.sub("-", (value or "").lower()).strip("-")
    return slug[:max_length].strip("-") or "request"


class GitHubWorkspaceManager:
    """Computes safe workspace *metadata* only.

    This service never talks to GitHub, never pushes commits, never merges, and
    never modifies a repository. It only proposes a branch name and reports
    whether a repository looks ready for a (future, separately gated) change.
    """

    BRANCH_PREFIX = "codedna/ai"

    def create_branch_name(self, request: EngineeringRequest) -> str:
        short_id = str(request.id)[:8] if isinstance(request.id, (str, uuid.UUID)) else "00000000"
        request_type = getattr(request.request_type, "value", str(request.request_type))
        slug = _slugify(request.title)
        return f"{self.BRANCH_PREFIX}/{request_type}-{short_id}-{slug}"

    def verify_default_branch(self, repository: Repository | None) -> str | None:
        return repository.default_branch if repository else None

    def is_branch_safe(self, branch_name: str, default_branch: str | None) -> bool:
        normalized = (branch_name or "").strip().lower()
        if not normalized.startswith(f"{self.BRANCH_PREFIX}/"):
            return False
        if normalized in PROTECTED_BRANCHES:
            return False
        if default_branch and normalized == default_branch.strip().lower():
            return False
        return True

    def validate_repository_state(
        self, repository: Repository | None, *, branch_name: str | None = None
    ) -> dict:
        """Return read-only metadata describing whether the repo looks executable."""
        issues: list[str] = []
        if repository is None:
            return {
                "repository_linked": False,
                "default_branch": None,
                "is_active": False,
                "branch_safe": False,
                "clean": False,
                "issues": ["No repository is associated with this request."],
            }

        default_branch = repository.default_branch
        is_active = bool(repository.is_active)
        repository_linked = repository.github_installation_id is not None

        if not is_active:
            issues.append("Repository is not active.")
        if not repository_linked:
            issues.append("Repository is not linked to a GitHub installation.")
        if not default_branch:
            issues.append("Repository has no default branch recorded.")

        branch_safe = True
        if branch_name is not None:
            branch_safe = self.is_branch_safe(branch_name, default_branch)
            if not branch_safe:
                issues.append("Proposed working branch is not safe (must be an isolated codedna/ai branch).")

        return {
            "repository_linked": repository_linked,
            "default_branch": default_branch,
            "is_active": is_active,
            "branch_safe": branch_safe,
            "clean": len(issues) == 0,
            "issues": issues,
        }
