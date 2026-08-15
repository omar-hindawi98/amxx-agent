"""Unit tests for Settings - env var loading and validation."""


def test_defaults():
    from amxx_agent.config import Settings

    s = Settings()
    assert s.host == "127.0.0.1"
    assert s.port == 27016
    assert s.max_concurrent == 32
    assert s.request_timeout_seconds == 60
    assert s.auth_token == ""
    assert s.model_backend == "ollama"
    assert s.model_name == "llama3.2:1b"
    assert s.model_tokens == 2048
    assert s.model_endpoint == ""
    assert s.model_api_key == ""
    assert s.memory_max_messages == 10


def test_backend_normalized_to_lowercase(monkeypatch):
    monkeypatch.setenv("AGENT_MODEL_BACKEND", "Ollama")
    from amxx_agent.config import Settings

    s = Settings()
    assert s.model_backend == "ollama"


def test_backend_all_caps_normalized(monkeypatch):
    monkeypatch.setenv("AGENT_MODEL_BACKEND", "BEDROCK")
    from amxx_agent.config import Settings

    s = Settings()
    assert s.model_backend == "bedrock"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("AGENT_HOST", "0.0.0.0")
    monkeypatch.setenv("AGENT_PORT", "9000")
    monkeypatch.setenv("AGENT_MODEL_API_KEY", "sk-test")
    monkeypatch.setenv("AGENT_MODEL_TOKENS", "1024")
    from amxx_agent.config import Settings

    s = Settings()
    assert s.host == "0.0.0.0"
    assert s.port == 9000
    assert s.model_api_key == "sk-test"
    assert s.model_tokens == 1024


def test_memory_path_under_home(monkeypatch):
    from pathlib import Path

    from amxx_agent.config import Settings

    monkeypatch.delenv("AGENT_MEMORY_PATH", raising=False)
    s = Settings()
    assert s.memory_path == Path.home() / ".local" / "share" / "amxx_agent" / "memory.db"


def test_skills_path_default_is_absolute():
    from pathlib import Path

    from amxx_agent.config import Settings

    s = Settings()
    assert s.skills_path == Path.home() / ".local" / "share" / "amxx_agent" / "skills"
    assert s.skills_path.is_absolute()


def test_skills_path_configurable(monkeypatch):
    from pathlib import Path

    monkeypatch.setenv("AGENT_SKILLS_PATH", "/opt/agent/skills")
    from amxx_agent.config import Settings

    s = Settings()
    assert s.skills_path == Path("/opt/agent/skills")


def test_auth_token_configurable(monkeypatch):
    monkeypatch.setenv("AGENT_AUTH_TOKEN", "supersecret")
    from amxx_agent.config import Settings

    s = Settings()
    assert s.auth_token == "supersecret"


def test_request_timeout_configurable(monkeypatch):
    monkeypatch.setenv("AGENT_REQUEST_TIMEOUT_SECONDS", "120")
    from amxx_agent.config import Settings

    s = Settings()
    assert s.request_timeout_seconds == 120
