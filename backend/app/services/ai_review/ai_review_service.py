from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import settings
from app.services.ai_review.limits import AIReviewLimitService
from app.services.ai_review.ollama_client import OllamaClient
from app.services.ai_review.pr_context_builder import PRContextBuilder
from app.services.ai_review.prompt_builder import AIReviewPromptBuilder
from app.services.types import ChangedFile
from app.services.ai_review.groq_client import GroqClient

logger = logging.getLogger(__name__)

REVIEW_SECTION_KEYS = (
    "summary",
    "security_issues",
    "bug_risks",
    "performance_concerns",
    "maintainability_suggestions",
    "recommended_action",
)


class AIReviewService:
    def __init__(
        self,
        *,
        client: OllamaClient | GroqClient | None = None,
        context_builder: PRContextBuilder | None = None,
        prompt_builder: AIReviewPromptBuilder | None = None,
        limit_service: AIReviewLimitService | None = None,
    ) -> None:
        provider = settings.ai_provider.lower()

        if client is not None:
            self.client = client
        elif provider == "groq":
            self.client = GroqClient()
        else:
            self.client = OllamaClient()

        self.provider = provider
        self.context_builder = context_builder or PRContextBuilder()
        self.prompt_builder = prompt_builder or AIReviewPromptBuilder()
        self.limit_service = limit_service or AIReviewLimitService()

    def review_files(self, files: list[ChangedFile]) -> dict[str, Any]:
        logger.info(
            "ai_review_started",
            extra={
                "ai_provider": self.provider,
                "ai_model": self.client.model,
                "file_count": len(files),
                "enabled": settings.ai_review_enabled,
            },
        )
        if not settings.ai_review_enabled:
            reason = "AI review skipped because AI_REVIEW_ENABLED is false."
            logger.info(
                "ai_review_skipped",
                extra={"ai_provider": self.provider, "ai_model": self.client.model, "reason": reason},
            )
            return self._skipped(reason)

        limit_result = self.limit_service.check_and_record(files)
        if not limit_result.allowed:
            reason = f"AI review skipped due to limit: {limit_result.reason}"
            logger.warning(
                "ai_review_skipped_due_to_limit",
                extra={
                    "ai_provider": self.provider,
                    "ai_model": self.client.model,
                    "reason": reason,
                },
            )
            return self._skipped(reason, skip_reason="limit_exceeded")

        try:
            logger.info(
                "ai_review_provider_selected",
                extra={"ai_provider": self.provider, "ai_model": self.client.model},
            )
            pr_context = self.context_builder.build(files)
            prompt = self.prompt_builder.build(pr_context=pr_context)
            raw = self.client.generate(prompt)
            payload = self._parse_payload(raw)
            review = self._normalize_review(payload)
            findings = self._normalize_findings(payload.get("findings"))
            logger.info(
                "ai_review_generated",
                extra={
                    "ai_provider": self.provider,
                    "ai_model": self.client.model,
                    "finding_count": len(findings),
                    "summary_chars": len(review["summary"]),
                },
            )
            return {
                "summary": review["summary"],
                "findings": findings,
                "review": review,
                "markdown": self._to_markdown(review),
                "model": self.client.model,
                "provider": self.provider,
                "enabled": True,
                "skipped": False,
            }
        except Exception as exc:
            error_message = str(exc)[:500]
            logger.exception(
                "ai_review_failed",
                extra={
                    "ai_provider": self.provider,
                    "ai_model": self.client.model,
                    "error": error_message,
                },
            )
            logger.warning(
                "ai_review_skipped",
                extra={
                    "ai_provider": self.provider,
                    "ai_model": self.client.model,
                    "reason": error_message,
                },
            )
            return self._skipped(f"AI review skipped because {self.provider} was unavailable or returned invalid output: {exc}")

    def _parse_payload(self, raw: str) -> dict[str, Any]:
        candidate = raw.strip()
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError as exc:
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start >= 0 and end > start:
                try:
                    payload = json.loads(candidate[start : end + 1])
                except json.JSONDecodeError:
                    logger.warning(
                        "ai_review_non_json",
                        extra={"ai_provider": self.provider, "raw_response": raw[:1000]},
                    )
                    raise ValueError(f"{self.provider} returned non-JSON review output") from exc
            else:
                logger.warning(
                    "ai_review_non_json",
                    extra={"ai_provider": self.provider, "raw_response": raw[:1000]},
                )
                raise ValueError(f"{self.provider} returned non-JSON review output") from exc

        if not isinstance(payload, dict):
            raise ValueError(f"{self.provider} review output must be a JSON object")
        return payload

    def _normalize_review(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "summary": self._string_value(payload.get("summary"), "AI review completed."),
            "security_issues": self._string_list(payload.get("security_issues")),
            "bug_risks": self._string_list(payload.get("bug_risks")),
            "performance_concerns": self._string_list(payload.get("performance_concerns")),
            "maintainability_suggestions": self._string_list(payload.get("maintainability_suggestions")),
            "recommended_action": self._string_value(payload.get("recommended_action"), "Review the findings before merging."),
        }

    def _normalize_findings(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []

        findings: list[dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            severity = str(item.get("severity") or "medium").lower()
            if severity not in {"low", "medium", "high", "critical"}:
                severity = "medium"
            line = item.get("line")
            findings.append(
                {
                    "source": "ai_review",
                    "severity": severity,
                    "title": self._string_value(item.get("title"), "AI review finding"),
                    "description": self._string_value(item.get("description"), ""),
                    "recommendation": self._string_value(item.get("recommendation"), ""),
                    "category": self._string_value(item.get("category"), "maintainability"),
                    "path": item.get("path") if isinstance(item.get("path"), str) else None,
                    "line": line if isinstance(line, int) else None,
                }
            )
        return findings

    def _to_markdown(self, review: dict[str, Any]) -> str:
        sections = [
            ("Summary", [review["summary"]]),
            ("Security issues", review["security_issues"]),
            ("Bug risks", review["bug_risks"]),
            ("Performance concerns", review["performance_concerns"]),
            ("Maintainability suggestions", review["maintainability_suggestions"]),
            ("Recommended action", [review["recommended_action"]]),
        ]
        lines: list[str] = []
        for title, values in sections:
            lines.append(f"### {title}")
            if values:
                lines.extend(f"- {value}" for value in values)
            else:
                lines.append("- None identified.")
            lines.append("")
        return "\n".join(lines).strip()

    def _skipped(self, message: str, *, skip_reason: str | None = None) -> dict[str, Any]:
        review = {
            "summary": message,
            "security_issues": [],
            "bug_risks": [],
            "performance_concerns": [],
            "maintainability_suggestions": [],
            "recommended_action": "Continue with rules-based review results.",
        }
        return {
            "summary": message,
            "findings": [],
            "review": review,
            "markdown": self._to_markdown(review),
            "model": self.client.model,
            "provider": self.provider,
            "enabled": False,
            "skipped": True,
            "skip_reason": skip_reason,
        }

    def _string_value(self, value: Any, default: str) -> str:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return default

    def _string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
