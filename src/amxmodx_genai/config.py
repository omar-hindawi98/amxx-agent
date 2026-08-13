"""Configuration values loaded from environment variables or a .env file."""

from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration for the GenAI sidecar.

    GENAI_* environment variables (or .env file) override the defaults below.
    memory_path and skills_path are fixed at runtime and not configurable via env.

    Server:
      GENAI_HOST, GENAI_PORT

    Model:
      GENAI_MODEL_BACKEND, GENAI_MODEL_NAME, GENAI_MODEL_TOKENS, GENAI_MODEL_ENDPOINT
    """

    model_config = SettingsConfigDict(
        env_prefix="GENAI_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    host: str = "127.0.0.1"
    port: int = 27016
    model_backend: str = "anthropic"
    model_name: str = "claude-haiku-4-5-20251001"
    model_tokens: int = 512
    model_endpoint: str = ""

    @computed_field
    @property
    def memory_path(self) -> Path:
        """SQLite database path for conversation memory."""
        return Path.home() / ".local" / "share" / "amxmodx_genai" / "memory.db"

    @computed_field
    @property
    def skills_path(self) -> Path:
        """Directory containing plugin skill definitions."""
        return Path("./skills")


settings = Settings()
