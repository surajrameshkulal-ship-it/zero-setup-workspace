"""Pluggable AI providers used by the AI Provider Router.

Each provider exposes a uniform interface (`name`, `model`, `is_available`,
`generate`). The base class emits the per-request logging events so every
provider behaves consistently. Adding a new cloud provider only requires a new
subclass registered in the router — no business-logic changes elsewhere.

Note: Ollama is intentionally NOT a provider here. CodeDNA does not require a
local model and never falls back to Ollama automatically.
"""

from __future__ import annotations

import logging
import time

from app.core.config import settings
from app.core.errors import IntegrationError
from app.services.ai_review.groq_client import GroqClient

logger = logging.getLogger(__name__)


class AIProvider:
    """Base class for AI providers.

    Subclasses implement `_generate`, `is_available`, and the `model` property.
    `generate` wraps `_generate` with consistent request logging.
    """

    name: str = "base"

    @property
    def model(self) -> str:  # pragma: no cover - overridden
        raise NotImplementedError

    def is_available(self) -> bool:  # pragma: no cover - overridden
        raise NotImplementedError

    def _generate(self, prompt: str) -> str:  # pragma: no cover - overridden
        raise NotImplementedError

    def generate(self, prompt: str) -> str:
        logger.info(
            "ai_provider_request_started",
            extra={"ai_provider": self.name, "ai_model": self.model, "prompt_chars": len(prompt)},
        )
        started_at = time.perf_counter()
        try:
            result = self._generate(prompt)
        except Exception as exc:  # noqa: BLE001 - logged then re-raised
            logger.warning(
                "ai_provider_failed",
                extra={"ai_provider": self.name, "ai_model": self.model, "error": str(exc)[:500]},
            )
            raise
        logger.info(
            "ai_provider_request_completed",
            extra={
                "ai_provider": self.name,
                "ai_model": self.model,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                "response_chars": len(result or ""),
            },
        )
        return result


class GroqProvider(AIProvider):
    """Default provider. Wraps the existing Groq client."""

    name = "groq"

    def __init__(self, client: GroqClient | None = None) -> None:
        self._client = client

    @property
    def client(self) -> GroqClient:
        if self._client is None:
            self._client = GroqClient()
        return self._client

    @property
    def model(self) -> str:
        return settings.groq_model

    def is_available(self) -> bool:
        return bool(settings.groq_api_key)

    def _generate(self, prompt: str) -> str:
        return self.client.generate(prompt)


class OpenAIProvider(AIProvider):
    """Placeholder. Configuration is read, but generation is not yet implemented."""

    name = "openai"

    @property
    def model(self) -> str:
        return settings.openai_model

    def is_available(self) -> bool:
        return bool(settings.openai_api_key)

    def _generate(self, prompt: str) -> str:
        raise IntegrationError(
            "The OpenAI provider is a placeholder and is not yet implemented. "
            "Set AI_PROVIDER=groq, or wait for the OpenAI provider implementation."
        )


class AnthropicProvider(AIProvider):
    """Placeholder. Configuration is read, but generation is not yet implemented."""

    name = "anthropic"

    @property
    def model(self) -> str:
        return settings.anthropic_model

    def is_available(self) -> bool:
        return bool(settings.anthropic_api_key)

    def _generate(self, prompt: str) -> str:
        raise IntegrationError(
            "The Anthropic provider is a placeholder and is not yet implemented. "
            "Set AI_PROVIDER=groq, or wait for the Anthropic provider implementation."
        )
