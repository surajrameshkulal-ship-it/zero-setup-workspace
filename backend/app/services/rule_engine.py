from __future__ import annotations
import fnmatch
import re
from typing import Iterable

from app.models.rule import CompanyRuleType
from app.services.types import ChangedFile, Finding


class CompanyRuleEngine:
    def check(self, files: list[ChangedFile], rules: Iterable[object]) -> list[dict]:
        violations: list[dict] = []
        for rule in rules:
            if not getattr(rule, "is_active", True):
                continue
            rule_type = getattr(rule, "rule_type")
            if hasattr(rule_type, "value"):
                rule_type = rule_type.value
            for file in files:
                finding = self._check_rule(file, rule, str(rule_type))
                if finding:
                    violations.append(finding.to_dict())
        return violations

    def _check_rule(self, file: ChangedFile, rule: object, rule_type: str) -> Finding | None:
        pattern = str(getattr(rule, "pattern"))
        severity = self._severity(rule)
        title = str(getattr(rule, "name"))
        description = str(getattr(rule, "description"))
        haystack = "\n".join([file.path, file.patch or "", file.content or ""])

        if rule_type == CompanyRuleType.REQUIRED_TEXT.value:
            if file.content is not None and pattern not in file.content:
                return Finding(
                    source="company_rule",
                    severity=severity,
                    title=title,
                    description=f"Required text is missing: {description}",
                    path=file.path,
                    recommendation=f"Add or preserve the required standard: {pattern}",
                    category="company_standard",
                    metadata={"rule_id": str(getattr(rule, "id", "")), "rule_type": rule_type},
                )

        if rule_type == CompanyRuleType.FORBIDDEN_TEXT.value:
            line = self._first_line_containing(file.content or file.patch, pattern)
            if pattern in haystack:
                return Finding(
                    source="company_rule",
                    severity=severity,
                    title=title,
                    description=f"Forbidden text matched: {description}",
                    path=file.path,
                    line=line,
                    recommendation="Remove or replace the forbidden pattern to comply with company standards.",
                    category="company_standard",
                    metadata={"rule_id": str(getattr(rule, "id", "")), "rule_type": rule_type},
                )

        if rule_type == CompanyRuleType.REGEX.value:
            match = re.search(pattern, haystack, flags=re.MULTILINE)
            if match:
                line = self._line_for_offset(haystack, match.start())
                return Finding(
                    source="company_rule",
                    severity=severity,
                    title=title,
                    description=f"Company regex rule matched: {description}",
                    path=file.path,
                    line=line,
                    recommendation="Refactor the matched code to satisfy this company rule.",
                    category="company_standard",
                    metadata={"rule_id": str(getattr(rule, "id", "")), "rule_type": rule_type},
                )

        if rule_type == CompanyRuleType.FILE_PATH.value:
            if fnmatch.fnmatch(file.path, pattern) or self._regex_matches(pattern, file.path):
                return Finding(
                    source="company_rule",
                    severity=severity,
                    title=title,
                    description=f"File path rule matched: {description}",
                    path=file.path,
                    recommendation="Move or rename the file so it follows repository conventions.",
                    category="company_standard",
                    metadata={"rule_id": str(getattr(rule, "id", "")), "rule_type": rule_type},
                )
        return None

    def _severity(self, rule: object) -> str:
        severity = getattr(rule, "severity", "medium")
        return severity.value if hasattr(severity, "value") else str(severity)

    def _first_line_containing(self, text: str, needle: str) -> int | None:
        for index, line in enumerate(text.splitlines(), start=1):
            if needle in line:
                return index
        return None

    def _line_for_offset(self, text: str, offset: int) -> int:
        return text[:offset].count("\n") + 1

    def _regex_matches(self, pattern: str, text: str) -> bool:
        try:
            return bool(re.search(pattern, text))
        except re.error:
            return False
