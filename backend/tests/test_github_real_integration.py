from __future__ import annotations

import io
import json
import tarfile
import uuid
from pathlib import Path

from app.integrations.github import GitHubIntegration
from app.models.github import GitHubInstallation
from app.services.agent.github_draft_pr_creator import DefaultDraftPRClient
from app.services.agent.github_source_provider import GitHubTarballSourceProvider


class FakeResponse:
    def __init__(self, status: int, body: dict) -> None:
        self.status_code = status
        self._body = body
        self.text = json.dumps(body)

    def json(self) -> dict:
        return self._body


class FakeSession:
    """Records HTTP calls and returns GitHub-shaped responses (proves real calls)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []

    def request(self, method, url, headers=None, params=None, json=None, timeout=None):
        self.calls.append((method, url, json))
        if method == "GET" and "/git/ref/heads/" in url:
            return FakeResponse(200, {"object": {"sha": "base123"}})
        if method == "POST" and url.endswith("/git/refs"):
            return FakeResponse(201, {"ref": "refs/heads/codedna/ai/x"})
        if method == "GET" and "/contents/" in url:
            return FakeResponse(404, {"message": "Not Found"})  # new file
        if method == "PUT" and "/contents/" in url:
            return FakeResponse(201, {"content": {"sha": "newsha"}})
        if method == "POST" and url.endswith("/pulls"):
            return FakeResponse(201, {"number": 7, "html_url": "https://github.com/o/r/pull/7"})
        return FakeResponse(200, {})


def test_default_client_issues_real_github_http(monkeypatch) -> None:
    gh = GitHubIntegration()
    gh.session = FakeSession()
    monkeypatch.setattr(gh, "get_installation_token", lambda installation_id: "tok")

    client = DefaultDraftPRClient(gh)
    client.push_branch(
        owner="o",
        repo="r",
        installation_id=1,
        branch="codedna/ai/x",
        base_branch="main",
        files=[("src/a.py", "x = 1\n")],
        deletions=[],
        message="feat: x",
    )
    pr = client.open_draft_pull_request(
        owner="o", repo="r", installation_id=1, head="codedna/ai/x", base="main", title="[CodeDNA AI] X", body="b"
    )

    method_urls = [(m, u) for (m, u, _) in gh.session.calls]
    # Real GitHub REST operations were issued (not simulated).
    assert any(m == "POST" and u.endswith("/git/refs") for m, u in method_urls), "branch not created"
    assert any(m == "PUT" and "/contents/src/a.py" in u for m, u in method_urls), "file not committed"
    assert any(m == "POST" and u.endswith("/pulls") for m, u in method_urls), "PR not created"
    assert pr["number"] == 7
    assert pr["html_url"].endswith("/pull/7")


def test_create_pull_request_sends_draft_true(monkeypatch) -> None:
    gh = GitHubIntegration()
    session = FakeSession()
    gh.session = session
    gh.create_pull_request(
        token="tok", owner="o", repo="r", head="codedna/ai/x", base="main", title="t", body="b", draft=True
    )
    post = next(j for (m, u, j) in session.calls if m == "POST" and u.endswith("/pulls"))
    assert post["draft"] is True
    assert post["head"] == "codedna/ai/x"
    assert post["base"] == "main"


def test_tarball_source_provider_extracts_real_files(api_context, tmp_path, monkeypatch) -> None:
    installation = GitHubInstallation(
        organization_id=api_context.organization.id,
        installation_id=999001,
        account_login="acme-labs",
        account_type="Organization",
        permissions={},
    )
    api_context.db.add(installation)
    api_context.db.flush()
    api_context.repository.github_installation_id = installation.id
    api_context.db.commit()

    # Build a GitHub-style tarball (single top-level dir that must be stripped).
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = b"print('hi')\n"
        info = tarfile.TarInfo(name="acme-labs-payments-api-abc123/src/app.py")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    tarball = buf.getvalue()

    gh = GitHubIntegration()
    monkeypatch.setattr(gh, "get_installation_token", lambda installation_id: "tok")
    monkeypatch.setattr(gh, "get_branch_sha", lambda **kw: "commitsha")
    monkeypatch.setattr(gh, "download_tarball", lambda **kw: tarball)

    provider = GitHubTarballSourceProvider(api_context.db, integration=gh)
    dest = tmp_path / "ws"
    dest.mkdir()
    meta = provider(api_context.repository, str(dest))

    assert (dest / "src/app.py").read_text() == "print('hi')\n"
    assert meta["commit_sha"] == "commitsha"
