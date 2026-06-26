from __future__ import annotations
import base64
import logging
import time
from typing import Any

import requests
from jose import jwt

from app.core.config import settings
from app.core.errors import IntegrationError
from app.services.types import ChangedFile

logger = logging.getLogger(__name__)


class GitHubIntegration:
    def __init__(self) -> None:
        self.base_url = str(settings.github_api_base_url).rstrip("/")
        self.session = requests.Session()

    def _app_jwt(self) -> str:
        if not settings.github_app_id or not settings.github_private_key:
            raise IntegrationError("GitHub App credentials are not configured")
        now = int(time.time())
        payload = {"iat": now - 60, "exp": now + 540, "iss": settings.github_app_id}
        return jwt.encode(payload, settings.github_private_key, algorithm="RS256")

    def _headers(self, token: str) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        token: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        log_full_error_body: bool = False,
    ) -> requests.Response:
        url = f"{self.base_url}{path}"
        response = self.session.request(method, url, headers=self._headers(token), params=params, json=json, timeout=30)
        if response.status_code >= 400:
            body = response.text
            logger.warning(
                "github_api_error",
                extra={
                    "status_code": response.status_code,
                    "method": method,
                    "path": path,
                    "body": body if log_full_error_body else body[:1000],
                },
            )
            detail = f": {body[:4000]}" if log_full_error_body and body else ""
            raise IntegrationError(
                f"GitHub API request failed with status {response.status_code}{detail}",
                upstream_status=response.status_code,
            )
        logger.info("github_api_response", extra={"status_code": response.status_code, "method": method, "path": path})
        return response

    def list_directory(self, *, token: str, owner: str, repo: str, path: str, ref: str) -> list[str]:
        """List file paths in a repository directory (read-only). Empty if absent."""
        try:
            response = self._request(
                "GET", f"/repos/{owner}/{repo}/contents/{path}", token=token, params={"ref": ref}
            )
        except IntegrationError:
            return []
        data = response.json()
        if not isinstance(data, list):
            return []
        return [item["path"] for item in data if isinstance(item, dict) and item.get("type") == "file"]

    def list_repository_tree(self, *, token: str, owner: str, repo: str, ref: str) -> list[str]:
        """List every file path in the repository (read-only, recursive).

        Uses the Git Trees API. Returns an empty list (never raises) if the tree
        cannot be read, so language inference can fall back to other evidence.
        """
        try:
            sha = self.get_branch_sha(token=token, owner=owner, repo=repo, branch=ref)
        except IntegrationError:
            sha = ref
        try:
            response = self._request(
                "GET",
                f"/repos/{owner}/{repo}/git/trees/{sha}",
                token=token,
                params={"recursive": "1"},
            )
        except IntegrationError:
            return []
        payload = response.json()
        tree = payload.get("tree", []) if isinstance(payload, dict) else []
        return [item["path"] for item in tree if isinstance(item, dict) and item.get("type") == "blob"]

    def download_tarball(self, *, token: str, owner: str, repo: str, ref: str) -> bytes:
        """Download a read-only tarball of the repository at a ref (no git binary)."""
        url = f"{self.base_url}/repos/{owner}/{repo}/tarball/{ref}"
        response = self.session.get(url, headers=self._headers(token), timeout=60, allow_redirects=True)
        if response.status_code >= 400:
            logger.warning(
                "github_api_error",
                extra={"status_code": response.status_code, "method": "GET", "path": f"/repos/{owner}/{repo}/tarball/{ref}"},
            )
            raise IntegrationError(f"GitHub tarball download failed with status {response.status_code}")
        logger.info("github_api_response", extra={"status_code": response.status_code, "method": "GET", "path": "tarball"})
        return response.content

    def get_installation_token(self, installation_id: int) -> str:
        app_token = self._app_jwt()
        response = self._request(
            "POST",
            f"/app/installations/{installation_id}/access_tokens",
            token=app_token,
        )
        payload = response.json()
        token = payload.get("token")
        if not token:
            raise IntegrationError("GitHub did not return an installation token")
        return token

    def list_installation_repositories(self, installation_id: int) -> list[dict[str, Any]]:
        token = self.get_installation_token(installation_id)
        repositories: list[dict[str, Any]] = []
        page = 1
        while True:
            response = self._request(
                "GET",
                "/installation/repositories",
                token=token,
                params={"per_page": 100, "page": page},
            )
            payload = response.json()
            repositories.extend(payload.get("repositories", []))
            if len(payload.get("repositories", [])) < 100:
                break
            page += 1
        return repositories

    def get_pull_request_files(
        self,
        *,
        installation_id: int,
        owner: str,
        repo: str,
        pr_number: int,
        head_sha: str,
    ) -> list[ChangedFile]:
        token = self.get_installation_token(installation_id)
        files: list[ChangedFile] = []
        page = 1
        while True:
            response = self._request(
                "GET",
                f"/repos/{owner}/{repo}/pulls/{pr_number}/files",
                token=token,
                params={"per_page": 100, "page": page},
            )
            batch = response.json()
            for item in batch:
                path = item["filename"]
                content = None
                if item.get("status") != "removed":
                    content = self.get_file_content(
                        token=token,
                        owner=owner,
                        repo=repo,
                        path=path,
                        ref=head_sha,
                    )
                files.append(
                    ChangedFile(
                        path=path,
                        status=item.get("status", "modified"),
                        patch=item.get("patch") or "",
                        additions=int(item.get("additions") or 0),
                        deletions=int(item.get("deletions") or 0),
                        content=content,
                    )
                )
            if len(batch) < 100:
                break
            page += 1
        return files

    def get_file_content(self, *, token: str, owner: str, repo: str, path: str, ref: str) -> str | None:
        response = self._request(
            "GET",
            f"/repos/{owner}/{repo}/contents/{path}",
            token=token,
            params={"ref": ref},
        )
        payload = response.json()
        if payload.get("type") != "file" or payload.get("encoding") != "base64":
            return None
        raw = payload.get("content", "")
        try:
            data = base64.b64decode(raw, validate=False)
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return None

    def get_branch_sha(self, *, token: str, owner: str, repo: str, branch: str) -> str:
        response = self._request("GET", f"/repos/{owner}/{repo}/git/ref/heads/{branch}", token=token)
        return response.json()["object"]["sha"]

    def create_branch(self, *, token: str, owner: str, repo: str, branch: str, sha: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/repos/{owner}/{repo}/git/refs",
            token=token,
            json={"ref": f"refs/heads/{branch}", "sha": sha},
        ).json()

    def get_content_sha(self, *, token: str, owner: str, repo: str, path: str, ref: str) -> str | None:
        try:
            response = self._request(
                "GET", f"/repos/{owner}/{repo}/contents/{path}", token=token, params={"ref": ref}
            )
        except IntegrationError:
            return None
        data = response.json()
        return data.get("sha") if isinstance(data, dict) else None

    def put_file(
        self, *, token: str, owner: str, repo: str, path: str, content_b64: str, message: str, branch: str, sha: str | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"message": message, "content": content_b64, "branch": branch}
        if sha:
            payload["sha"] = sha
        return self._request("PUT", f"/repos/{owner}/{repo}/contents/{path}", token=token, json=payload).json()

    def delete_file(
        self, *, token: str, owner: str, repo: str, path: str, message: str, branch: str, sha: str
    ) -> dict[str, Any]:
        return self._request(
            "DELETE",
            f"/repos/{owner}/{repo}/contents/{path}",
            token=token,
            json={"message": message, "branch": branch, "sha": sha},
        ).json()

    def create_pull_request(
        self, *, token: str, owner: str, repo: str, head: str, base: str, title: str, body: str, draft: bool = True
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/repos/{owner}/{repo}/pulls",
            token=token,
            json={"head": head, "base": base, "title": title, "body": body, "draft": draft},
        ).json()

    def list_pull_requests(
        self, *, token: str, owner: str, repo: str, head: str | None = None, state: str = "all"
    ) -> list[dict[str, Any]]:
        """List pull requests, optionally filtered by head (``owner:branch``)."""
        params: dict[str, Any] = {"state": state, "per_page": 100}
        if head:
            params["head"] = head
        response = self._request("GET", f"/repos/{owner}/{repo}/pulls", token=token, params=params)
        data = response.json()
        return data if isinstance(data, list) else []

    def create_pr_comment(
        self,
        *,
        installation_id: int,
        owner: str,
        repo: str,
        pr_number: int,
        body: str,
    ) -> dict[str, Any]:
        token = self.get_installation_token(installation_id)
        response = self._request(
            "POST",
            f"/repos/{owner}/{repo}/issues/{pr_number}/comments",
            token=token,
            json={"body": body},
        )
        return response.json()

    def create_check_run(
        self,
        *,
        installation_id: int,
        owner: str,
        repo: str,
        name: str,
        head_sha: str,
        status: str,
        output: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = self.get_installation_token(installation_id)
        payload: dict[str, Any] = {
            "name": name,
            "head_sha": head_sha,
            "status": status,
        }
        if output:
            payload["output"] = output
        logger.info(
            "github_check_run_create",
            extra={"owner": owner, "repo": repo, "check_run_name": name, "head_sha": head_sha, "status": status},
        )
        response = self._request(
            "POST",
            f"/repos/{owner}/{repo}/check-runs",
            token=token,
            json=payload,
            log_full_error_body=True,
        )
        result = response.json()
        logger.info(
            "github_check_run_create_response",
            extra={
                "owner": owner,
                "repo": repo,
                "check_run_name": name,
                "head_sha": head_sha,
                "status_code": response.status_code,
                "check_run_id": result.get("id"),
            },
        )
        return result

    def update_check_run(
        self,
        *,
        installation_id: int,
        owner: str,
        repo: str,
        check_run_id: int,
        status: str,
        conclusion: str | None = None,
        completed_at: str | None = None,
        output: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = self.get_installation_token(installation_id)
        payload: dict[str, Any] = {"status": status}
        if conclusion:
            payload["conclusion"] = conclusion
        if completed_at:
            payload["completed_at"] = completed_at
        if output:
            payload["output"] = output
        logger.info(
            "github_check_run_update",
            extra={
                "owner": owner,
                "repo": repo,
                "check_run_id": check_run_id,
                "status": status,
                "conclusion": conclusion,
            },
        )
        response = self._request(
            "PATCH",
            f"/repos/{owner}/{repo}/check-runs/{check_run_id}",
            token=token,
            json=payload,
        )
        return response.json()
