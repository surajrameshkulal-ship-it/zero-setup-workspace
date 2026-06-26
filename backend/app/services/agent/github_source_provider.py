"""Real GitHub source provider for the Repository Materializer.

Performs a READ-ONLY checkout of a repository into the workspace by downloading
the GitHub tarball with the App installation token and extracting it (no git
binary, no write to the remote). Used so the AI pipeline operates on the real
source before changes are pushed back as a draft PR.
"""

from __future__ import annotations

import io
import logging
import tarfile
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.errors import IntegrationError
from app.integrations.github import GitHubIntegration
from app.models.github import GitHubInstallation
from app.models.repository import Repository

logger = logging.getLogger(__name__)


class GitHubTarballSourceProvider:
    """Callable: (repository, dest_path) -> {"commit_sha": ...}. Extracts the repo tarball."""

    def __init__(self, db: Session, *, integration: GitHubIntegration | None = None) -> None:
        self.db = db
        self.gh = integration or GitHubIntegration()

    def __call__(self, repository: Repository, dest_path: str) -> dict:
        if repository.github_installation_id is None:
            raise IntegrationError("Repository is not connected to a GitHub installation.")
        installation = self.db.get(GitHubInstallation, repository.github_installation_id)
        if installation is None:
            raise IntegrationError("GitHub installation is missing.")

        token = self.gh.get_installation_token(installation.installation_id)
        ref = repository.default_branch or "main"
        commit_sha = None
        try:
            commit_sha = self.gh.get_branch_sha(token=token, owner=repository.owner, repo=repository.name, branch=ref)
        except IntegrationError:
            pass

        tarball = self.gh.download_tarball(token=token, owner=repository.owner, repo=repository.name, ref=ref)
        self._extract(tarball, Path(dest_path))
        logger.info(
            "repository_source_checked_out",
            extra={"repository": repository.full_name, "ref": ref, "commit_sha": commit_sha},
        )
        return {"commit_sha": commit_sha}

    @staticmethod
    def _extract(tarball: bytes, dest: Path) -> None:
        dest = dest.resolve()
        with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as tar:
            for member in tar.getmembers():
                # GitHub tarballs nest everything under a single top-level dir; strip it.
                parts = Path(member.name).parts
                if len(parts) <= 1:
                    continue
                rel = Path(*parts[1:])
                target = (dest / rel).resolve()
                # Defense in depth: never write outside the destination workspace.
                if dest not in target.parents and target != dest:
                    continue
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    extracted = tar.extractfile(member)
                    if extracted is not None:
                        target.write_bytes(extracted.read())
