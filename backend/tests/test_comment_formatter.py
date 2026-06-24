from __future__ import annotations
from app.services.comment_formatter import PRCommentFormatter


def test_comment_formatter_includes_risk_and_findings() -> None:
    body = PRCommentFormatter().format(
        {
            "summary": "Review complete.",
            "risk": {"level": "medium", "score": 42},
            "files_changed": 2,
            "lines_added": 15,
            "lines_deleted": 4,
            "semgrep_findings": [
                {
                    "severity": "high",
                    "path": "app/main.py",
                    "line": 12,
                    "title": "SQL injection",
                    "description": "Unsafe query construction.",
                }
            ],
            "ai_findings": [],
            "company_rule_violations": [],
            "architecture_violations": [],
        }
    )

    assert "CodeDNA AI Review" in body
    assert "MEDIUM (42/100)" in body
    assert "`app/main.py:12`" in body

