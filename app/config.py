from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["openai", "anthropic", "google", "groq"]


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    database_url: str
    model_provider: str = "openai"
    model_name: str = "gpt-4o-mini"
    system_prompt: str = "You are a helpful AI assistant."
    request_timeout_seconds: float = Field(default=60.0, gt=0)

    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    groq_api_key: str | None = None

    @property
    def normalized_provider(self) -> str:
        return self.model_provider.strip().lower()

    @property
    def model_identifier(self) -> str:
        prefixes = {
            "openai": "openai",
            "anthropic": "anthropic",
            "google": "google",
            "groq": "groq",
        }
        prefix = prefixes.get(self.normalized_provider)
        if prefix is None:
            supported = ", ".join(prefixes)
            raise ValueError(
                f"Unsupported MODEL_PROVIDER '{self.model_provider}'. Supported: {supported}."
            )
        name = self.model_name.strip()
        if not name:
            raise ValueError("MODEL_NAME must not be empty.")
        return f"{prefix}:{name}"

    @property
    def provider_api_key(self) -> str | None:
        keys = {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "google": self.google_api_key,
            "groq": self.groq_api_key,
        }
        value = keys.get(self.normalized_provider)
        return value.strip() if value and value.strip() else None

    @property
    def provider_key_name(self) -> str:
        return f"{self.normalized_provider.upper()}_API_KEY"


@lru_cache
def get_settings() -> Settings:
    return Settings()
