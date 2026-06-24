from __future__ import annotations
import json
import logging

from openai import OpenAI

from app.core.config import settings
from app.services.types import ChangedFile

logger = logging.getLogger(__name__)


class OpenAIReviewClient:
    def __init__(self) -> None:
        self.model = settings.openai_model
        self.client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    def review_files(self, files: list[ChangedFile]) -> dict:
        if not self.client:
            return {
                "summary": "AI review skipped because OPENAI_API_KEY is not configured.",
                "findings": [],
                "model": self.model,
                "enabled": False,
            }

        prompt = self._build_prompt(files)
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are CodeDNA AI, a senior application security and architecture reviewer. "
                        "Return strict JSON with keys: summary, findings. Findings must be an array of "
                        "objects with path, line, severity, title, description, recommendation, category."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        raw = response.choices[0].message.content or "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("openai_review_non_json", extra={"raw": raw[:1000]})
            return {
                "summary": "AI review completed, but the response could not be parsed as JSON.",
                "findings": [],
                "model": self.model,
                "enabled": True,
            }

        findings = payload.get("findings", [])
        if not isinstance(findings, list):
            findings = []
        return {
            "summary": str(payload.get("summary") or "AI review completed."),
            "findings": [finding for finding in findings if isinstance(finding, dict)],
            "model": self.model,
            "enabled": True,
        }

    def _build_prompt(self, files: list[ChangedFile]) -> str:
        parts = [
            "Review the following pull request changes for correctness, security, reliability, maintainability, "
            "architecture drift, and risky migrations. Prefer precise findings over broad advice.",
        ]
        for file in files[:40]:
            patch = file.patch[:12000]
            content_excerpt = (file.content or "")[:8000]
            parts.append(
                "\n".join(
                    [
                        f"FILE: {file.path}",
                        f"STATUS: {file.status}",
                        f"ADDITIONS: {file.additions}",
                        f"DELETIONS: {file.deletions}",
                        "PATCH:",
                        patch,
                        "CURRENT_FILE_EXCERPT:",
                        content_excerpt,
                    ]
                )
            )
        return "\n\n---\n\n".join(parts)[:100000]

