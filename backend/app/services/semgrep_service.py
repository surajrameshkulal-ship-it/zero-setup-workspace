from __future__ import annotations
import json
import logging
import subprocess
import tempfile
from pathlib import Path

from app.core.config import settings
from app.services.types import ChangedFile, Finding
from app.utils.pathing import safe_relative_path

logger = logging.getLogger(__name__)


class SemgrepService:
    def scan_files(self, files: list[ChangedFile]) -> list[dict]:
        writable_files = [file for file in files if file.content and file.status != "removed"]
        if not writable_files:
            return []

        with tempfile.TemporaryDirectory(prefix="codedna-semgrep-") as tmp_dir:
            root = Path(tmp_dir)
            for file in writable_files:
                safe_path = safe_relative_path(file.path)
                if not safe_path:
                    continue
                target = (root / safe_path).resolve()
                if not str(target).startswith(str(root.resolve())):
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(file.content or "", encoding="utf-8")

            command = [
                settings.semgrep_binary,
                "scan",
                "--config",
                settings.semgrep_config,
                "--json",
                str(root),
            ]
            try:
                completed = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=settings.semgrep_timeout_seconds,
                )
            except FileNotFoundError:
                logger.warning("semgrep_binary_missing", extra={"binary": settings.semgrep_binary})
                return [
                    Finding(
                        source="semgrep",
                        severity="medium",
                        title="Semgrep is not installed",
                        description="The configured Semgrep binary could not be found in the worker container.",
                        recommendation="Install Semgrep in the backend image or update SEMGREP_BINARY.",
                        category="scanner_configuration",
                    ).to_dict()
                ]
            except subprocess.TimeoutExpired:
                logger.warning("semgrep_timeout", extra={"timeout": settings.semgrep_timeout_seconds})
                return [
                    Finding(
                        source="semgrep",
                        severity="medium",
                        title="Semgrep scan timed out",
                        description=f"Semgrep did not finish within {settings.semgrep_timeout_seconds} seconds.",
                        recommendation="Reduce scan scope or increase SEMGREP_TIMEOUT_SECONDS.",
                        category="scanner_timeout",
                    ).to_dict()
                ]

            if completed.stderr:
                logger.info("semgrep_stderr", extra={"stderr": completed.stderr[:1000]})
            try:
                payload = json.loads(completed.stdout or "{}")
            except json.JSONDecodeError:
                logger.warning("semgrep_invalid_json", extra={"stdout": completed.stdout[:1000]})
                return [
                    Finding(
                        source="semgrep",
                        severity="medium",
                        title="Semgrep returned invalid JSON",
                        description="The Semgrep process completed but its JSON output could not be parsed.",
                        recommendation="Check Semgrep configuration and worker logs.",
                        category="scanner_output",
                    ).to_dict()
                ]

            return [self._normalize_result(result, root) for result in payload.get("results", [])]

    def _normalize_result(self, result: dict, root: Path) -> dict:
        path = result.get("path")
        if path:
            try:
                path = str(Path(path).resolve().relative_to(root.resolve()))
            except ValueError:
                path = str(path)
        extra = result.get("extra") or {}
        start = result.get("start") or {}
        return Finding(
            source="semgrep",
            severity=str(extra.get("severity") or "medium").lower(),
            title=str(result.get("check_id") or "Semgrep finding"),
            description=str(extra.get("message") or "Semgrep reported a finding."),
            path=path,
            line=start.get("line"),
            recommendation=extra.get("fix") or extra.get("metadata", {}).get("recommendation"),
            category=str(extra.get("metadata", {}).get("category") or "static_analysis"),
            metadata={"check_id": result.get("check_id"), "metadata": extra.get("metadata", {})},
        ).to_dict()

