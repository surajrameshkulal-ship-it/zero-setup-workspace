from __future__ import annotations

import logging
from typing import Any

import requests

from app.core.config import settings
from app.core.errors import IntegrationError

logger = logging.getLogger(__name__)


class OllamaClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.base_url = str(base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model
        self.timeout_seconds = timeout_seconds or settings.ollama_timeout_seconds

    def generate(self, prompt: str) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,
                "top_p": 0.9,
            },
        }
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise IntegrationError(f"Ollama is unavailable: {exc}") from exc

        if response.status_code >= 400:
            logger.warning(
                "ollama_api_error",
                extra={
                    "status_code": response.status_code,
                    "ollama_base_url": self.base_url,
                    "ollama_model": self.model,
                    "body": response.text[:1000],
                },
            )
            raise IntegrationError(f"Ollama API request failed with status {response.status_code}")

        payload = response.json()
        generated = payload.get("response")
        if not isinstance(generated, str):
            raise IntegrationError("Ollama response did not include generated text")
        return generated.strip()
