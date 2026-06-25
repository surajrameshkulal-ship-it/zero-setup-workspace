from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from app.core.config import settings
from app.core.errors import AppError
from app.models.rule import CompanyRule, CompanyRuleType, Severity
from app.services.agent.validation_runner import RunOutcome, ValidationRunner


def _ws(tmp_path, files: dict[str, str] | None = None) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    for rel, content in (files or {}).items():
        target = ws / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return ws


def _fixed(outcome: RunOutcome):
    def run_command(argv, *, cwd, timeout, env):
        run_command.calls.append({"argv": argv, "cwd": cwd, "timeout": timeout, "env": env})
        return outcome
    run_command.calls = []
    return run_command


def test_pytest_success(tmp_path) -> None:
    ws = _ws(tmp_path)
    runner = ValidationRunner(ws, run_command=_fixed(RunOutcome("2 passed", "", 0)))
    result = runner.run_one("pytest")
    assert result.status == "passed"
    assert result.exit_code == 0
    assert result.command == "python -m pytest"
    assert result.duration_ms >= 0


def test_pytest_failure(tmp_path) -> None:
    ws = _ws(tmp_path)
    runner = ValidationRunner(ws, run_command=_fixed(RunOutcome("1 failed", "trace", 1)))
    result = runner.run_one("pytest")
    assert result.status == "failed"
    assert result.exit_code == 1
    assert "exited with code 1" in result.failure_summary


def test_npm_build_success(tmp_path) -> None:
    ws = _ws(tmp_path, {"package.json": json.dumps({"scripts": {"build": "next build"}})})
    runner = ValidationRunner(ws, run_command=_fixed(RunOutcome("compiled", "", 0)))
    result = runner.run_one("npm_build")
    assert result.status == "passed"
    assert result.command == "npm run build"


def test_npm_build_skipped_without_script(tmp_path) -> None:
    ws = _ws(tmp_path)  # no package.json
    runner = ValidationRunner(ws, run_command=_fixed(RunOutcome("", "", 0)))
    result = runner.run_one("npm_build")
    assert result.status == "skipped"


def test_command_timeout(tmp_path) -> None:
    ws = _ws(tmp_path)
    runner = ValidationRunner(ws, run_command=_fixed(RunOutcome("", "", 124, timed_out=True)), timeout_seconds=30)
    result = runner.run_one("pytest")
    assert result.status == "failed"
    assert "timed out" in result.failure_summary


def test_disallowed_command_rejected(tmp_path) -> None:
    ws = _ws(tmp_path)
    runner = ValidationRunner(ws, run_command=_fixed(RunOutcome("", "", 0)))
    with pytest.raises(AppError):
        runner.run_one("rm")
    with pytest.raises(AppError):
        runner.run(["curl"])


def test_invalid_workspace_rejected(tmp_path) -> None:
    with pytest.raises(AppError):
        ValidationRunner(tmp_path / "does-not-exist")


def test_output_redaction(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "groq_api_key", "supersecretvalue123")
    ws = _ws(tmp_path)
    leaky = "GROQ_API_KEY=sk-secret-abc123\nusing key supersecretvalue123 now\n"
    runner = ValidationRunner(ws, run_command=_fixed(RunOutcome(leaky, "", 1)))
    result = runner.run_one("pytest")
    assert "sk-secret-abc123" not in result.stdout_excerpt
    assert "supersecretvalue123" not in result.stdout_excerpt
    assert "[REDACTED]" in result.stdout_excerpt


def test_sanitized_env_excludes_secrets(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "should-not-pass")
    ws = _ws(tmp_path)
    rc = _fixed(RunOutcome("ok", "", 0))
    runner = ValidationRunner(ws, run_command=rc)
    runner.run_one("pytest")
    passed_env = rc.calls[0]["env"]
    assert "GROQ_API_KEY" not in passed_env
    assert "PATH" in passed_env


def test_codedna_rule_validation_called(api_context, tmp_path) -> None:
    ws = _ws(tmp_path, {"app/main.py": "x = eval(payload)\n"})
    api_context.db.add(
        CompanyRule(
            organization_id=api_context.organization.id,
            name="No eval",
            description="eval forbidden",
            rule_type=CompanyRuleType.FORBIDDEN_TEXT,
            pattern="eval(",
            severity=Severity.HIGH,
        )
    )
    api_context.db.commit()
    runner = ValidationRunner(ws, db=api_context.db, organization_id=api_context.organization.id)
    result = runner.run_one("codedna_rules")
    assert result.status == "failed"
    assert "No eval" in result.failure_summary


def test_codedna_rules_pass_when_clean(api_context, tmp_path) -> None:
    ws = _ws(tmp_path, {"app/main.py": "x = 1\n"})
    api_context.db.add(
        CompanyRule(
            organization_id=api_context.organization.id,
            name="No eval",
            description="eval forbidden",
            rule_type=CompanyRuleType.FORBIDDEN_TEXT,
            pattern="eval(",
            severity=Severity.HIGH,
        )
    )
    api_context.db.commit()
    runner = ValidationRunner(ws, db=api_context.db, organization_id=api_context.organization.id)
    result = runner.run_one("codedna_rules")
    assert result.status == "passed"
