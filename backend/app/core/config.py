from __future__ import annotations
from functools import lru_cache
from typing import Any

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CodeDNA AI"
    api_v1_prefix: str = "/api/v1"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    secret_key: str = Field(..., min_length=16)
    access_token_expire_minutes: int = 60 * 24
    allowed_origins: list[str] = ["http://localhost:3000"]

    database_url: str
    redis_url: str = "redis://redis:6379/0"

    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"

    ai_provider: str = "groq"
    ai_review_enabled: bool = True
    ai_review_timeout_seconds: int = 60
    ai_daily_request_limit: int = 0
    ai_monthly_request_limit: int = 0
    ai_max_files_per_review: int = 40
    ai_max_diff_chars: int = 80000
    groq_api_key: str | None = None
    groq_model: str = "llama-3.1-8b-instant"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-3-5-sonnet-latest"
    ollama_base_url: AnyHttpUrl = "http://host.docker.internal:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_timeout_seconds: int = 120

    github_app_id: str | None = None
    github_app_slug: str | None = None
    github_private_key: str | None = None
    github_webhook_secret: str
    github_api_base_url: AnyHttpUrl = "https://api.github.com"

    semgrep_binary: str = "semgrep"
    semgrep_config: str = "auto"
    semgrep_timeout_seconds: int = 120

    # Secure workspace manager (Phase 10). Isolated temp dirs for future AI code
    # execution. If workspace_root is unset, a dedicated subdir of the system
    # temp directory is used. workspaces are never created outside this base.
    workspace_root: str | None = None
    workspace_max_size_mb: int = 50

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("github_private_key", mode="before")
    @classmethod
    def normalize_private_key(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.replace("\\n", "\n")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
