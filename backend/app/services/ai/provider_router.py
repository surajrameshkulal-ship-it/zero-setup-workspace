"""AI Provider Router.

Single point that selects an AI provider based on configuration and routes
generation requests to it. Supports `groq` (default), `openai`, `anthropic`,
and `auto`. It never falls back to Ollama and returns a clear error when the
selected provider is unavailable. New providers are added by registering a new
provider instance — business logic does not change.
"""

from __future__ import annotations

import logging

from app.core.config import settings
from app.core.errors import IntegrationError
from app.services.ai.providers import (
    AIProvider,
    AnthropicProvider,
    GroqProvider,
    OpenAIProvider,
)

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER = "groq"
# Order used when AI_PROVIDER=auto. Ollama is intentionally excluded.
AUTO_ORDER = ("groq", "openai", "anthropic")
SUPPORTED = ("groq", "openai", "anthropic", "auto")


class AIProviderRouter:
    def __init__(self, *, providers: dict[str, AIProvider] | None = None) -> None:
        self._providers: dict[str, AIProvider] = providers or {
            "groq": GroqProvider(),
            "openai": OpenAIProvider(),
            "anthropic": AnthropicProvider(),
        }

    def select(self, name: str | None = None) -> AIProvider:
        """Resolve and return the provider to use, logging the selection."""
        requested = (name or settings.ai_provider or DEFAULT_PROVIDER).strip().lower()

        if requested == "auto":
            for candidate in AUTO_ORDER:
                provider = self._providers.get(candidate)
                if provider is not None and provider.is_available():
                    logger.info(
                        "ai_provider_selected",
                        extra={"ai_provider": provider.name, "selection_mode": "auto"},
                    )
                    return provider
            logger.warning("ai_provider_failed", extra={"ai_provider": "auto", "reason": "no_available_provider"})
            raise IntegrationError(
                "No AI provider is available. Configure GROQ_API_KEY (default) or another supported provider."
            )

        provider = self._providers.get(requested)
        if provider is None:
            logger.warning(
                "ai_provider_failed",
                extra={"ai_provider": requested, "reason": "unknown_provider"},
            )
            raise IntegrationError(
                f"Unknown AI provider '{requested}'. Supported providers: {', '.join(SUPPORTED)}."
            )
        logger.info(
            "ai_provider_selected",
            extra={"ai_provider": provider.name, "selection_mode": "explicit"},
        )
        return provider

    def generate(self, prompt: str, *, name: str | None = None) -> str:
        """Select a provider and route a generation request to it.

        Raises a clear error if the selected provider is unavailable. The
        per-request logging (started/completed/failed) is emitted by the
        provider itself.
        """
        provider = self.select(name)
        if not provider.is_available():
            logger.warning(
                "ai_provider_failed",
                extra={"ai_provider": provider.name, "reason": "unavailable"},
            )
            raise IntegrationError(
                f"AI provider '{provider.name}' is not available. "
                "Check its API key and configuration."
            )
        return provider.generate(prompt)


_router: AIProviderRouter | None = None


def get_ai_router() -> AIProviderRouter:
    """Return a shared router instance."""
    global _router
    if _router is None:
        _router = AIProviderRouter()
    return _router
