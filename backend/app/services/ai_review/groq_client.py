from __future__ import annotations

import logging
import time

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)


class GroqClient:
    def __init__(self) -> None:
        self.api_key = settings.groq_api_key
        self.model = settings.groq_model
        self.base_url = "https://api.groq.com/openai/v1"
        self.timeout = settings.ai_review_timeout_seconds

    def generate(self, prompt: str) -> str:
        if not self.api_key:
            raise ValueError("GROQ_API_KEY is missing")

        logger.info(
            "groq_review_request_started",
            extra={
                "ai_provider": "groq",
                "groq_model": self.model,
                "prompt_chars": len(prompt),
                "timeout_seconds": self.timeout,
            },
        )
        started_at = time.perf_counter()
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a senior code reviewer. Return only valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 1200,
            },
            timeout=self.timeout,
        )
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.info(
            "groq_review_request_completed",
            extra={
                "ai_provider": "groq",
                "groq_model": self.model,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        if response.status_code >= 400:
            logger.warning(
                "groq_review_request_failed",
                extra={
                    "ai_provider": "groq",
                    "groq_model": self.model,
                    "status_code": response.status_code,
                    "response_body": response.text[:1000],
                },
            )
            response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
