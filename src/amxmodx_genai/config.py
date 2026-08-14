"""Configuration values loaded from environment variables or a .env file."""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration for the GenAI sidecar.

    GENAI_* environment variables (or .env file) override the defaults below.

    Server:
      GENAI_HOST, GENAI_PORT, GENAI_MAX_CONCURRENT, GENAI_REQUEST_TIMEOUT_SECONDS,
      GENAI_AUTH_TOKEN

    Model:
      GENAI_MODEL_BACKEND, GENAI_MODEL_NAME, GENAI_MODEL_TOKENS,
      GENAI_MODEL_ENDPOINT, GENAI_MODEL_API_KEY

    Memory:
      GENAI_MEMORY_MAX_MESSAGES, GENAI_MEMORY_PATH

    Skills:
      GENAI_SKILLS_PATH
    """

    model_config = SettingsConfigDict(
        env_prefix="GENAI_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    log_level: str = "INFO"
    host: str = "127.0.0.1"
    port: int = 27016
    max_concurrent: int = 32
    # Per-request LLM timeout in seconds. 0 disables the timeout.
    request_timeout_seconds: int = 60
    # When non-empty, every query/clear_memory message must include a matching auth_token field.
    auth_token: str = ""
    model_backend: str = "anthropic"
    model_name: str = "claude-haiku-4-5-20251001"
    model_tokens: int = 2048
    model_endpoint: str = ""
    model_api_key: str = ""
    memory_max_messages: int = 20

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, v: object) -> str:
        return str(v).upper()

    @field_validator("model_backend", mode="before")
    @classmethod
    def _normalize_backend(cls, v: object) -> str:
        """Lowercase the backend name so 'Ollama' and 'OLLAMA' both work."""
        return str(v).lower()

    memory_path: Path = Path.home() / ".local" / "share" / "amxmodx_genai" / "memory.db"
    skills_path: Path = Path.home() / ".local" / "share" / "amxmodx_genai" / "skills"


settings = Settings()
