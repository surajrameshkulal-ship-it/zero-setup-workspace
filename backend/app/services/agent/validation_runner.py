"""Real Validation Runner (Phase 10, Step 6).

Executes an allowlisted set of validation commands INSIDE an isolated workspace
and runs CodeDNA rule validation using the existing rule engines. It never
merges, deploys, pushes, or bypasses human approval.

Safety model:
  * command allowlist only (no arbitrary commands, never shell=True)
  * per-command timeout and bounded output capture
  * commands run with a sanitized environment (no secrets exposed)
  * working directory is the workspace; an invalid workspace is rejected
  * secrets/env values are redacted from captured output
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.models.rule import ArchitectureRule, CompanyRule
from app.services.architecture_checker import ArchitectureRuleChecker
from app.services.rule_engine import CompanyRuleEngine
from app.services.types import ChangedFile

logger = logging.getLogger(__name__)

# name -> argv. Never includes a shell, network tools, or git mutations.
ALLOWED_COMMANDS: dict[str, list[str]] = {
    "pytest": ["python", "-m", "pytest"],
    "npm_build": ["npm", "run", "build"],
    "npm_lint": ["npm", "run", "lint"],
    "semgrep": ["semgrep", "scan", "--quiet", "--error"],
}
RULE_CHECK = "codedna_rules"
DEFAULT_COMMANDS = ["pytest", "npm_build", "npm_lint", "semgrep", RULE_CHECK]

DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_MAX_OUTPUT_CHARS = 4000

# Files we never read for rule validation.
_FORBIDDEN_SEGMENTS = re.compile(r"(^|/)\.env|(^|/)\.git/|secret|credential|\.pem$|\.key$|id_rsa")
_TEXT_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".rb", ".php", ".sql", ".sh", ".md", ".json", ".yaml", ".yml", ".toml"}

# Redact "key: value" / "key=value" style secrets in captured output.
_REDACT_RE = re.compile(
    r"(?i)((?:secret|secret[_-]?key|token|api[_-]?key|password|authorization|private[_-]?key)\s*[:=]\s*)(\S+)"
)


@dataclass
class RunOutcome:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False
    missing_binary: bool = False


@dataclass
class CommandResult:
    name: str
    command: str
    status: str  # passed | failed | skipped
    exit_code: int | None
    duration_ms: float
    stdout_excerpt: str
    stderr_excerpt: str
    failure_summary: str | None

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "command": self.command,
            "status": self.status,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "stdout_excerpt": self.stdout_excerpt,
            "stderr_excerpt": self.stderr_excerpt,
            "failure_summary": self.failure_summary,
        }


class ValidationRunner:
    def __init__(
        self,
        workspace_path: str | os.PathLike,
        *,
        db: Session | None = None,
        organization_id: uuid.UUID | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
        run_command: Callable[..., RunOutcome] | None = None,
        rule_file_limit: int = 500,
    ) -> None:
        path = Path(workspace_path)
        if not workspace_path or not path.is_dir():
            raise AppError("Invalid workspace: a real workspace directory is required.")
        self.workspace = path.resolve()
        self.db = db
        self.organization_id = organization_id
        self.timeout_seconds = timeout_seconds
        self.max_output_chars = max_output_chars
        self._run_command = run_command or self._subprocess_run
        self.rule_file_limit = rule_file_limit

    # -- public API ------------------------------------------------------------

    def run(self, commands: list[str] | None = None) -> list[CommandResult]:
        names = commands if commands is not None else list(DEFAULT_COMMANDS)
        results: list[CommandResult] = []
        for name in names:
            results.append(self.run_one(name))
        return results

    def run_one(self, name: str) -> CommandResult:
        if name == RULE_CHECK:
            return self._run_codedna_rules()
        if name not in ALLOWED_COMMANDS:
            raise AppError(f"Command '{name}' is not on the validation allowlist.")
        return self._run_allowed(name)

    # -- allowlisted shell commands --------------------------------------------

    def _run_allowed(self, name: str) -> CommandResult:
        argv = ALLOWED_COMMANDS[name]
        command_str = " ".join(argv)

        skip_reason = self._skip_reason(name)
        if skip_reason:
            return CommandResult(name, command_str, "skipped", None, 0.0, "", "", skip_reason)

        started = time.perf_counter()
        outcome = self._run_command(
            argv, cwd=str(self.workspace), timeout=self.timeout_seconds, env=self._sanitized_env()
        )
        duration_ms = round((time.perf_counter() - started) * 1000, 2)

        if outcome.missing_binary:
            return CommandResult(name, command_str, "skipped", None, duration_ms, "", "", "command not available")

        stdout = self._redact(outcome.stdout or "")[: self.max_output_chars]
        stderr = self._redact(outcome.stderr or "")[: self.max_output_chars]

        if outcome.timed_out:
            return CommandResult(
                name, command_str, "failed", None, duration_ms, stdout, stderr,
                f"{command_str} timed out after {self.timeout_seconds}s",
            )

        # pytest exit code 5 means "no tests collected" — treat as skipped.
        if name == "pytest" and outcome.exit_code == 5:
            return CommandResult(name, command_str, "skipped", 5, duration_ms, stdout, stderr, "no tests collected")

        status = "passed" if outcome.exit_code == 0 else "failed"
        failure = None if status == "passed" else f"{command_str} exited with code {outcome.exit_code}"
        return CommandResult(name, command_str, status, outcome.exit_code, duration_ms, stdout, stderr, failure)

    def _skip_reason(self, name: str) -> str | None:
        if name in ("npm_build", "npm_lint"):
            pkg = self.workspace / "package.json"
            if not pkg.is_file():
                return "no package.json"
            script = "build" if name == "npm_build" else "lint"
            try:
                scripts = json.loads(pkg.read_text(encoding="utf-8")).get("scripts", {})
            except (ValueError, OSError):
                return "package.json unreadable"
            if script not in scripts:
                return f"no '{script}' script"
        if name == "semgrep" and shutil.which("semgrep") is None:
            return "semgrep not installed"
        return None

    def _subprocess_run(self, argv: list[str], *, cwd: str, timeout: int, env: dict) -> RunOutcome:
        try:
            completed = subprocess.run(  # noqa: S603 - argv list, shell=False, allowlisted
                argv,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
            )
        except FileNotFoundError:
            return RunOutcome(stdout="", stderr="", exit_code=127, missing_binary=True)
        except subprocess.TimeoutExpired as exc:
            return RunOutcome(stdout=exc.stdout or "", stderr=exc.stderr or "", exit_code=124, timed_out=True)
        return RunOutcome(stdout=completed.stdout, stderr=completed.stderr, exit_code=completed.returncode)

    @staticmethod
    def _sanitized_env() -> dict:
        # Minimal environment: never expose application secrets to the command.
        keep = {}
        for key in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT"):
            if os.environ.get(key):
                keep[key] = os.environ[key]
        keep["CODEDNA_SANDBOX"] = "1"
        keep["NODE_ENV"] = "production"
        return keep

    def _redact(self, text: str) -> str:
        redacted = _REDACT_RE.sub(r"\1[REDACTED]", text)
        for secret in (
            settings.secret_key,
            settings.groq_api_key,
            settings.openai_api_key,
            settings.anthropic_api_key,
            settings.github_private_key,
            settings.github_webhook_secret,
        ):
            if secret and len(str(secret)) >= 4:
                redacted = redacted.replace(str(secret), "[REDACTED]")
        return redacted

    # -- CodeDNA rule validation (existing engines) ----------------------------

    def _run_codedna_rules(self) -> CommandResult:
        if self.db is None or self.organization_id is None:
            return CommandResult(RULE_CHECK, RULE_CHECK, "skipped", None, 0.0, "", "", "no rule context")

        started = time.perf_counter()
        files = self._workspace_changed_files()
        company_rules = self.db.scalars(
            select(CompanyRule).where(
                CompanyRule.organization_id == self.organization_id,
                CompanyRule.is_active.is_(True),
            )
        ).all()
        architecture_rules = self.db.scalars(
            select(ArchitectureRule).where(
                ArchitectureRule.organization_id == self.organization_id,
                ArchitectureRule.is_active.is_(True),
            )
        ).all()

        violations = CompanyRuleEngine().check(files, company_rules)
        violations += ArchitectureRuleChecker().check(files, architecture_rules)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)

        if not company_rules and not architecture_rules:
            return CommandResult(RULE_CHECK, RULE_CHECK, "skipped", 0, duration_ms, "", "", "no rules configured")

        if violations:
            titles = ", ".join(sorted({str(v.get("title", "rule")) for v in violations}))
            summary = f"{len(violations)} rule violation(s): {titles}"
            return CommandResult(RULE_CHECK, RULE_CHECK, "failed", 1, duration_ms, "", "", summary)
        return CommandResult(RULE_CHECK, RULE_CHECK, "passed", 0, duration_ms, "", "", None)

    def _workspace_changed_files(self) -> list[ChangedFile]:
        files: list[ChangedFile] = []
        for root, dirs, names in os.walk(self.workspace, topdown=True):
            if ".git" in dirs:
                dirs.remove(".git")
            for name in names:
                abs_path = Path(root) / name
                rel = str(abs_path.relative_to(self.workspace))
                if _FORBIDDEN_SEGMENTS.search(rel.lower()):
                    continue
                if abs_path.suffix.lower() not in _TEXT_EXTS:
                    continue
                try:
                    content = abs_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                files.append(
                    ChangedFile(path=rel, status="modified", patch="", additions=0, deletions=0, content=content)
                )
                if len(files) >= self.rule_file_limit:
                    return files
        return files


def build_runner_validator(runner: ValidationRunner) -> Callable[[dict, int], list[dict]]:
    """Adapt a ValidationRunner into a ValidationService validator callable.

    Skipped commands are reported as non-failing so they do not block the gate.
    """

    def validator(context: dict, attempt: int) -> list[dict]:
        checks: list[dict] = []
        for result in runner.run():
            checks.append(
                {
                    "name": result.name,
                    "status": result.status,
                    "details": result.failure_summary or result.command,
                }
            )
        return checks

    return validator
