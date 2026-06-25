from __future__ import annotations

import json
import logging

from app.core.config import settings
from app.services.ai_review.ai_review_service import AIReviewService
from app.services.ai_review.pr_context_builder import PRContextBuilder, PRContextLimits
from app.services.check_run_report import CheckRunReportBuilder
from app.services.types import ChangedFile


class FakeAIClient:
    model = "llama3.1:8b"

    def __init__(self, payload: dict | None = None, error: Exception | None = None) -> None:
        self.payload = payload or {}
        self.error = error
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return json.dumps(self.payload)


class FakeLimitService:
    def __init__(self, *, allowed: bool = True, reason: str | None = None) -> None:
        self.allowed = allowed
        self.reason = reason
        self.calls = 0

    def check_and_record(self, files):
        from app.services.ai_review.limits import AIReviewLimitResult

        self.calls += 1
        return AIReviewLimitResult(allowed=self.allowed, reason=self.reason)


def changed_files() -> list[ChangedFile]:
    return [
        ChangedFile(
            path="src/app.ts",
            status="modified",
            patch="+ console.log(user.token)\n+ return result",
            additions=2,
            deletions=0,
            content="export function run() { console.log(user.token); }",
        )
    ]


def test_ai_review_parses_structured_review(monkeypatch, caplog) -> None:
    monkeypatch.setattr(settings, "ai_review_enabled", True)
    caplog.set_level(logging.INFO)
    client = FakeAIClient(
        {
            "summary": "The PR is small but exposes sensitive data in logs.",
            "security_issues": ["Avoid logging user tokens."],
            "bug_risks": ["No error handling was added."],
            "performance_concerns": [],
            "maintainability_suggestions": ["Move logging behind a debug guard."],
            "recommended_action": "Block merge until token logging is removed.",
            "findings": [
                {
                    "path": "src/app.ts",
                    "line": 1,
                    "severity": "high",
                    "title": "Sensitive token logged",
                    "description": "The patch logs user.token.",
                    "recommendation": "Remove the log statement.",
                    "category": "security",
                }
            ],
        }
    )

    limit_service = FakeLimitService()

    result = AIReviewService(client=client, limit_service=limit_service).review_files(changed_files())

    assert result["enabled"] is True
    assert result["provider"] == settings.ai_provider.lower()
    assert result["model"] == "llama3.1:8b"
    assert result["review"]["security_issues"] == ["Avoid logging user tokens."]
    assert result["review"]["recommended_action"] == "Block merge until token logging is removed."
    assert result["findings"][0]["source"] == "ai_review"
    assert result["findings"][0]["severity"] == "high"
    assert "### Security issues" in result["markdown"]
    assert "src/app.ts" in client.prompts[0]
    assert "ai_review_started" in caplog.messages
    assert "ai_review_provider_selected" in caplog.messages
    assert "ai_review_generated" in caplog.messages
    assert limit_service.calls == 1


def test_ai_review_skips_without_failing_scan(monkeypatch, caplog) -> None:
    monkeypatch.setattr(settings, "ai_review_enabled", True)
    caplog.set_level(logging.INFO)
    client = FakeAIClient(error=RuntimeError("connection refused"))

    result = AIReviewService(client=client, limit_service=FakeLimitService()).review_files(changed_files())

    assert result["enabled"] is False
    assert result["skipped"] is True
    assert result["findings"] == []
    assert "AI review skipped" in result["summary"]
    assert "ai_review_failed" in caplog.messages
    assert "ai_review_skipped" in caplog.messages


def test_ai_review_skips_when_limit_exceeded(monkeypatch, caplog) -> None:
    monkeypatch.setattr(settings, "ai_review_enabled", True)
    caplog.set_level(logging.INFO)
    client = FakeAIClient({"summary": "Should not be called"})
    limit_service = FakeLimitService(allowed=False, reason="daily AI review request limit 1 reached")

    result = AIReviewService(client=client, limit_service=limit_service).review_files(changed_files())

    assert result["enabled"] is False
    assert result["skipped"] is True
    assert result["skip_reason"] == "limit_exceeded"
    assert "AI review skipped due to limit" in result["summary"]
    assert client.prompts == []
    assert "ai_review_skipped_due_to_limit" in caplog.messages


def test_pr_context_builder_limits_prompt_size() -> None:
    context = PRContextBuilder(
        PRContextLimits(max_files=1, max_patch_chars_per_file=10, max_content_chars_per_file=5, max_total_chars=500)
    ).build(
        [
            ChangedFile(
                path="src/large.ts",
                status="modified",
                patch="+" * 100,
                additions=100,
                deletions=0,
                content="x" * 100,
            ),
            ChangedFile(
                path="src/omitted.ts",
                status="modified",
                patch="+ omitted",
                additions=1,
                deletions=0,
                content=None,
            ),
        ]
    )

    assert "FILE 1: src/large.ts" in context
    assert "src/omitted.ts" not in context
    assert "...[truncated]" in context
    assert "1 additional files were omitted" in context


def test_check_run_output_includes_ai_review_sections() -> None:
    output = CheckRunReportBuilder().build_completed_output(
        {
            "risk": {"score": 20, "level": "low"},
            "semgrep_findings": [],
            "ai_findings": [],
            "company_rule_violations": [],
            "architecture_violations": [],
            "ai": {"enabled": True, "provider": "ollama", "model": "llama3.1:8b"},
            "ai_review": {
                "summary": "The PR is easy to review.",
                "security_issues": [],
                "bug_risks": ["Input validation may be incomplete."],
                "performance_concerns": [],
                "maintainability_suggestions": ["Add a focused unit test."],
                "recommended_action": "Request a small follow-up test.",
            },
        }
    )

    assert "### AI Review" in output["summary"]
    assert "**Summary**" in output["summary"]
    assert "The PR is easy to review." in output["summary"]
    assert "**Bug risks**" in output["summary"]
    assert "Input validation may be incomplete." in output["summary"]


def test_check_run_output_includes_ai_limit_skip_reason() -> None:
    output = CheckRunReportBuilder().build_completed_output(
        {
            "risk": {"score": 10, "level": "low"},
            "semgrep_findings": [],
            "ai_findings": [],
            "company_rule_violations": [],
            "architecture_violations": [],
            "ai": {"enabled": False, "skipped": True, "skip_reason": "limit_exceeded"},
            "ai_review": {
                "summary": "AI review skipped due to limit: daily AI review request limit 1000 reached.",
            },
        }
    )

    assert "### AI Review" in output["summary"]
    assert "AI review skipped due to limit" in output["summary"]
