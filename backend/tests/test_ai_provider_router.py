from __future__ import annotations

import logging

import pytest

from app.core.config import settings
from app.core.errors import IntegrationError
from app.services.ai.provider_router import AIProviderRouter
from app.services.ai.providers import AIProvider, AnthropicProvider, GroqProvider, OpenAIProvider


class FakeProvider(AIProvider):
    def __init__(self, name: str, *, available: bool, text: str = "ok") -> None:
        self.name = name
        self._available = available
        self._text = text

    @property
    def model(self) -> str:
        return f"{self.name}-model"

    def is_available(self) -> bool:
        return self._available

    def _generate(self, prompt: str) -> str:
        return self._text


def test_default_selects_groq(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_provider", "groq")
    provider = AIProviderRouter().select()
    assert isinstance(provider, GroqProvider)
    assert provider.name == "groq"


def test_explicit_openai_and_anthropic_select(monkeypatch) -> None:
    router = AIProviderRouter()
    assert isinstance(router.select("openai"), OpenAIProvider)
    assert isinstance(router.select("anthropic"), AnthropicProvider)


def test_unknown_provider_raises_clear_error() -> None:
    with pytest.raises(IntegrationError) as exc:
        AIProviderRouter().select("definitely-not-a-provider")
    assert "Unknown AI provider" in str(exc.value)


def test_router_never_selects_ollama() -> None:
    router = AIProviderRouter()
    assert "ollama" not in router._providers
    with pytest.raises(IntegrationError):
        router.select("ollama")


def test_auto_picks_first_available() -> None:
    router = AIProviderRouter(
        providers={
            "groq": FakeProvider("groq", available=False),
            "openai": FakeProvider("openai", available=True, text="from-openai"),
            "anthropic": FakeProvider("anthropic", available=False),
        }
    )
    provider = router.select("auto")
    assert provider.name == "openai"


def test_auto_with_none_available_raises() -> None:
    router = AIProviderRouter(
        providers={
            "groq": FakeProvider("groq", available=False),
            "openai": FakeProvider("openai", available=False),
            "anthropic": FakeProvider("anthropic", available=False),
        }
    )
    with pytest.raises(IntegrationError) as exc:
        router.select("auto")
    assert "No AI provider is available" in str(exc.value)


def test_generate_routes_to_provider() -> None:
    router = AIProviderRouter(providers={"groq": FakeProvider("groq", available=True, text="hello")})
    assert router.generate("prompt", name="groq") == "hello"


def test_generate_unavailable_returns_clear_error() -> None:
    router = AIProviderRouter(providers={"groq": FakeProvider("groq", available=False)})
    with pytest.raises(IntegrationError) as exc:
        router.generate("prompt", name="groq")
    assert "not available" in str(exc.value)


def test_openai_provider_placeholder_generate_raises(monkeypatch) -> None:
    monkeypatch.setattr(settings, "openai_api_key", "configured")
    provider = OpenAIProvider()
    assert provider.is_available() is True
    with pytest.raises(IntegrationError) as exc:
        provider.generate("x")
    assert "placeholder" in str(exc.value).lower()


def test_anthropic_provider_placeholder_generate_raises(monkeypatch) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", "configured")
    provider = AnthropicProvider()
    assert provider.is_available() is True
    with pytest.raises(IntegrationError):
        provider.generate("x")


def test_logging_events_emitted(monkeypatch, caplog) -> None:
    caplog.set_level(logging.INFO)
    router = AIProviderRouter(providers={"groq": FakeProvider("groq", available=True, text="hi")})
    router.generate("prompt", name="groq")
    messages = {record.message for record in caplog.records}
    assert "ai_provider_selected" in messages
    assert "ai_provider_request_started" in messages
    assert "ai_provider_request_completed" in messages


def test_logging_failed_event(monkeypatch, caplog) -> None:
    caplog.set_level(logging.INFO)

    class Boom(FakeProvider):
        def _generate(self, prompt: str) -> str:
            raise RuntimeError("kaboom")

    router = AIProviderRouter(providers={"groq": Boom("groq", available=True)})
    with pytest.raises(RuntimeError):
        router.generate("prompt", name="groq")
    assert "ai_provider_failed" in {record.message for record in caplog.records}
