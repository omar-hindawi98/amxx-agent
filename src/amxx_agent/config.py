"""Configuration values loaded from environment variables or a .env file."""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration for the GenAI sidecar.

    AGENT_* environment variables (or .env file) override the defaults below.

    Server:
      AGENT_HOST, AGENT_PORT, AGENT_MAX_CONCURRENT, AGENT_REQUEST_TIMEOUT_SECONDS,
      AGENT_AUTH_TOKEN

    Model:
      AGENT_MODEL_BACKEND, AGENT_MODEL_NAME, AGENT_MODEL_TOKENS,
      AGENT_MODEL_ENDPOINT, AGENT_MODEL_API_KEY

    Memory:
      AGENT_MEMORY_MAX_MESSAGES, AGENT_MEMORY_PATH

    Skills:
      AGENT_SKILLS_PATH
    """

    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
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
    model_backend: str = "ollama"
    model_name: str = "llama3.2:1b"
    model_tokens: int = 2048
    model_endpoint: str = ""
    model_api_key: str = ""
    memory_max_messages: int = 10
    # Sessions not written to in this many days are removed by the vacuum task.
    # 0 disables vacuum entirely.
    memory_session_ttl_days: int = 0
    # Max concurrent in-flight requests per session_id. Raise above 1 for shared
    # sessions used by multiple players simultaneously (e.g. team sessions).
    session_concurrency: int = 1

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, v: object) -> str:
        return str(v).upper()

    @field_validator("model_backend", mode="before")
    @classmethod
    def _normalize_backend(cls, v: object) -> str:
        """Lowercase the backend name so 'Ollama' and 'OLLAMA' both work."""
        return str(v).lower()

    memory_path: Path = Path.home() / ".local" / "share" / "amxx_agent" / "memory.db"
    skills_path: Path = Path.home() / ".local" / "share" / "amxx_agent" / "skills"


settings = Settings()
