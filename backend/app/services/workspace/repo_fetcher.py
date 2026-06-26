"""Read-only repository fetch into an isolated workspace (Phase 11, Step 5).

Clones the repository at its default branch into the sandbox workspace using a
short-lived GitHub App installation token. This is a read-only checkout: the
sandbox never pushes, commits, or otherwise modifies the real repository.
"""

from __future__ import annotations

import logging
import subprocess

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.integrations.github import GitHubIntegration
from app.models.github import GitHubInstallation

logger = logging.getLogger(__name__)

CLONE_TIMEOUT_SECONDS = 180


class GitRepoFetcher:
    def __init__(self, db: Session, *, integration: GitHubIntegration | None = None) -> None:
        self.db = db
        self.gh = integration or GitHubIntegration()

    def fetch(self, repository, dest: str) -> None:
        if repository is None:
            raise AppError("Repository is required to fetch the workspace source.")
        if repository.github_installation_id is None:
            raise AppError("Repository is not connected to a GitHub installation.")
        installation = self.db.get(GitHubInstallation, repository.github_installation_id)
        if installation is None:
            raise AppError("GitHub installation is missing for this repository.")

        token = self.gh.get_installation_token(installation.installation_id)
        branch = repository.default_branch or "main"
        # Token is embedded only in the local clone URL for this one command.
        url = f"https://x-access-token:{token}@github.com/{repository.owner}/{repository.name}.git"
        try:
            proc = subprocess.run(
                ["git", "clone", "--depth", "1", "--branch", branch, url, dest],
                capture_output=True,
                text=True,
                timeout=CLONE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise AppError(f"Repository clone timed out after {CLONE_TIMEOUT_SECONDS}s.") from exc
        except OSError as exc:
            raise AppError(f"git is not available to clone the repository: {exc}") from exc
        if proc.returncode != 0:
            # Redact the token from any surfaced error output.
            stderr = (proc.stderr or "").replace(token, "***")
            raise AppError(f"Repository clone failed: {stderr.strip()[:300]}")
        logger.info("workspace_repo_fetched", extra={"repository": repository.full_name, "branch": branch})
