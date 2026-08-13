"""Configuration values loaded from environment variables or a .env file."""

from pathlib import Path

from pydantic import computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration for the GenAI sidecar.

    GENAI_* environment variables (or .env file) override the defaults below.
    memory_path and skills_path are fixed at runtime and not configurable via env.

    Server:
      GENAI_HOST, GENAI_PORT, GENAI_MAX_CONCURRENT

    Model:
      GENAI_MODEL_BACKEND, GENAI_MODEL_NAME, GENAI_MODEL_TOKENS,
      GENAI_MODEL_ENDPOINT, GENAI_MODEL_API_KEY

    Memory:
      GENAI_MEMORY_MAX_MESSAGES
    """

    model_config = SettingsConfigDict(
        env_prefix="GENAI_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    host: str = "127.0.0.1"
    port: int = 27016
    max_concurrent: int = 32
    model_backend: str = "anthropic"
    model_name: str = "claude-haiku-4-5-20251001"
    model_tokens: int = 512
    model_endpoint: str = ""
    model_api_key: str = ""
    memory_max_messages: int = 20

    @field_validator("model_backend", mode="before")
    @classmethod
    def _normalize_backend(cls, v: object) -> str:
        """Lowercase the backend name so 'Ollama' and 'OLLAMA' both work."""
        return str(v).lower()

    memory_path: Path = Path.home() / ".local" / "share" / "amxmodx_genai" / "memory.db"

    @computed_field
    @property
    def skills_path(self) -> Path:
        """Directory for plugin skill definitions. Relative to the working directory."""
        return Path("./skills")


settings = Settings()
