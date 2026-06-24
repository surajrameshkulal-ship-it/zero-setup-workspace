from __future__ import annotations
import fnmatch
import re
from typing import Iterable

from app.services.types import ChangedFile, Finding


IMPORT_PATTERNS = [
    re.compile(r"^\s*import\s+.+", re.MULTILINE),
    re.compile(r"^\s*from\s+[\w.]+\s+import\s+.+", re.MULTILINE),
    re.compile(r"require\(['\"]([^'\"]+)['\"]\)"),
    re.compile(r"from\s+['\"]([^'\"]+)['\"]"),
]


class ArchitectureRuleChecker:
    def check(self, files: list[ChangedFile], rules: Iterable[object]) -> list[dict]:
        violations: list[dict] = []
        for rule in rules:
            if not getattr(rule, "is_active", True):
                continue
            source_pattern = str(getattr(rule, "source_path_pattern"))
            forbidden_pattern = str(getattr(rule, "forbidden_import_pattern"))
            for file in files:
                if not self._path_matches(file.path, source_pattern):
                    continue
                violations.extend(self._check_file(file, rule, forbidden_pattern))
        return violations

    def _check_file(self, file: ChangedFile, rule: object, forbidden_pattern: str) -> list[dict]:
        text = file.content or file.patch or ""
        compiled = re.compile(forbidden_pattern)
        findings: list[dict] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not self._looks_like_import(line):
                continue
            if compiled.search(line):
                findings.append(
                    Finding(
                        source="architecture_rule",
                        severity=self._severity(rule),
                        title=str(getattr(rule, "name")),
                        description=str(getattr(rule, "description")),
                        path=file.path,
                        line=line_number,
                        recommendation="Change the dependency direction or introduce an approved boundary abstraction.",
                        category="architecture",
                        metadata={
                            "rule_id": str(getattr(rule, "id", "")),
                            "forbidden_import_pattern": forbidden_pattern,
                            "line": line.strip(),
                        },
                    ).to_dict()
                )
        return findings

    def _looks_like_import(self, line: str) -> bool:
        return any(pattern.search(line) for pattern in IMPORT_PATTERNS)

    def _path_matches(self, path: str, pattern: str) -> bool:
        if fnmatch.fnmatch(path, pattern):
            return True
        try:
            return bool(re.search(pattern, path))
        except re.error:
            return False

    def _severity(self, rule: object) -> str:
        severity = getattr(rule, "severity", "high")
        return severity.value if hasattr(severity, "value") else str(severity)
