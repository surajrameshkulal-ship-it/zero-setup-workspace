from __future__ import annotations
from types import SimpleNamespace

from app.models.rule import CompanyRuleType, Severity
from app.services.rule_engine import CompanyRuleEngine
from app.services.types import ChangedFile


def test_forbidden_text_rule_detects_patch_content() -> None:
    rule = SimpleNamespace(
        id="rule-1",
        name="No debug prints",
        description="Debug output must not be committed.",
        rule_type=CompanyRuleType.FORBIDDEN_TEXT,
        pattern="console.log",
        severity=Severity.MEDIUM,
        is_active=True,
    )
    files = [
        ChangedFile(
            path="frontend/app/page.tsx",
            status="modified",
            patch="+ console.log('debug')",
            additions=1,
            deletions=0,
            content="export default function Page() { console.log('debug'); }",
        )
    ]

    violations = CompanyRuleEngine().check(files, [rule])

    assert len(violations) == 1
    assert violations[0]["source"] == "company_rule"
    assert violations[0]["path"] == "frontend/app/page.tsx"


def test_required_text_rule_flags_missing_standard() -> None:
    rule = SimpleNamespace(
        id="rule-2",
        name="License header",
        description="Every source file needs a license header.",
        rule_type=CompanyRuleType.REQUIRED_TEXT,
        pattern="Copyright CodeDNA",
        severity=Severity.LOW,
        is_active=True,
    )
    files = [
        ChangedFile(
            path="backend/app/main.py",
            status="modified",
            patch="",
            additions=1,
            deletions=0,
            content="print('hello')",
        )
    ]

    violations = CompanyRuleEngine().check(files, [rule])

    assert len(violations) == 1
    assert violations[0]["severity"] == "low"

