"""Unit tests for the model factory - validate() and _build_model() dispatch."""

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# validate()
# ---------------------------------------------------------------------------


def test_validate_anthropic_with_key(monkeypatch):
    monkeypatch.setenv("GENAI_MODEL_BACKEND", "anthropic")
    monkeypatch.setenv("GENAI_MODEL_API_KEY", "sk-test")
    import importlib

    import amxmodx_genai.config as cfg

    cfg.settings = cfg.Settings()
    import amxmodx_genai.core.model as m

    importlib.reload(m)
    m.validate()  # should not raise


def test_validate_anthropic_no_key_raises(monkeypatch):
    monkeypatch.setenv("GENAI_MODEL_BACKEND", "anthropic")
    monkeypatch.delenv("GENAI_MODEL_API_KEY", raising=False)
    import importlib

    import amxmodx_genai.config as cfg

    cfg.settings = cfg.Settings()
    import amxmodx_genai.core.model as m

    importlib.reload(m)
    with pytest.raises(RuntimeError, match="GENAI_MODEL_API_KEY"):
        m.validate()


def test_validate_bedrock_no_key_ok(monkeypatch):
    monkeypatch.setenv("GENAI_MODEL_BACKEND", "bedrock")
    monkeypatch.delenv("GENAI_MODEL_API_KEY", raising=False)
    import importlib

    import amxmodx_genai.config as cfg

    cfg.settings = cfg.Settings()
    import amxmodx_genai.core.model as m

    importlib.reload(m)
    m.validate()  # bedrock does not need an API key


def test_validate_ollama_no_key_ok(monkeypatch):
    monkeypatch.setenv("GENAI_MODEL_BACKEND", "ollama")
    monkeypatch.delenv("GENAI_MODEL_API_KEY", raising=False)
    import importlib

    import amxmodx_genai.config as cfg

    cfg.settings = cfg.Settings()
    import amxmodx_genai.core.model as m

    importlib.reload(m)
    m.validate()


def test_validate_openai_no_key_raises(monkeypatch):
    monkeypatch.setenv("GENAI_MODEL_BACKEND", "openai")
    monkeypatch.delenv("GENAI_MODEL_API_KEY", raising=False)
    import importlib

    import amxmodx_genai.config as cfg

    cfg.settings = cfg.Settings()
    import amxmodx_genai.core.model as m

    importlib.reload(m)
    with pytest.raises(RuntimeError, match="GENAI_MODEL_API_KEY"):
        m.validate()


def test_validate_litellm_no_key_raises(monkeypatch):
    monkeypatch.setenv("GENAI_MODEL_BACKEND", "litellm")
    monkeypatch.delenv("GENAI_MODEL_API_KEY", raising=False)
    import importlib

    import amxmodx_genai.config as cfg

    cfg.settings = cfg.Settings()
    import amxmodx_genai.core.model as m

    importlib.reload(m)
    with pytest.raises(RuntimeError, match="GENAI_MODEL_API_KEY"):
        m.validate()


# ---------------------------------------------------------------------------
# _build_model() backend dispatch
# ---------------------------------------------------------------------------


def _reload_model_module(monkeypatch, backend: str, api_key: str = "", endpoint: str = ""):
    monkeypatch.setenv("GENAI_MODEL_BACKEND", backend)
    if api_key:
        monkeypatch.setenv("GENAI_MODEL_API_KEY", api_key)
    else:
        monkeypatch.delenv("GENAI_MODEL_API_KEY", raising=False)
    if endpoint:
        monkeypatch.setenv("GENAI_MODEL_ENDPOINT", endpoint)
    else:
        monkeypatch.delenv("GENAI_MODEL_ENDPOINT", raising=False)

    import importlib

    import amxmodx_genai.config as cfg

    cfg.settings = cfg.Settings()
    import amxmodx_genai.core.model as m

    importlib.reload(m)
    return m


def test_build_model_anthropic(monkeypatch):
    mock_cls = MagicMock(return_value=MagicMock())
    with patch.dict(
        "sys.modules", {"strands.models.anthropic": MagicMock(AnthropicModel=mock_cls)}
    ):
        m = _reload_model_module(monkeypatch, "anthropic", api_key="sk-x")
        m._build_model()
    mock_cls.assert_called_once()
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["client_args"] == {"api_key": "sk-x"}


def test_build_model_anthropic_no_key_empty_client_args(monkeypatch):
    mock_cls = MagicMock(return_value=MagicMock())
    with patch.dict(
        "sys.modules", {"strands.models.anthropic": MagicMock(AnthropicModel=mock_cls)}
    ):
        m = _reload_model_module(monkeypatch, "anthropic", api_key="")
        m._build_model()
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["client_args"] == {}


def test_build_model_bedrock(monkeypatch):
    mock_cls = MagicMock(return_value=MagicMock())
    with patch.dict("sys.modules", {"strands.models.bedrock": MagicMock(BedrockModel=mock_cls)}):
        m = _reload_model_module(monkeypatch, "bedrock")
        m._build_model()
    mock_cls.assert_called_once()


def test_build_model_ollama_default_endpoint(monkeypatch):
    mock_cls = MagicMock(return_value=MagicMock())
    with patch.dict("sys.modules", {"strands.models.ollama": MagicMock(OllamaModel=mock_cls)}):
        m = _reload_model_module(monkeypatch, "ollama")
        m._build_model()
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["host"] == "http://localhost:11434"


def test_build_model_ollama_custom_endpoint(monkeypatch):
    mock_cls = MagicMock(return_value=MagicMock())
    with patch.dict("sys.modules", {"strands.models.ollama": MagicMock(OllamaModel=mock_cls)}):
        m = _reload_model_module(monkeypatch, "ollama", endpoint="http://myhost:11434")
        m._build_model()
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["host"] == "http://myhost:11434"


def test_build_model_litellm_with_key_and_endpoint(monkeypatch):
    mock_cls = MagicMock(return_value=MagicMock())
    with patch.dict("sys.modules", {"strands.models.litellm": MagicMock(LiteLLMModel=mock_cls)}):
        m = _reload_model_module(monkeypatch, "litellm", api_key="sk-l", endpoint="http://proxy")
        m._build_model()
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["client_args"]["api_key"] == "sk-l"
    assert kwargs["client_args"]["base_url"] == "http://proxy"


def test_build_model_openai_with_key(monkeypatch):
    mock_cls = MagicMock(return_value=MagicMock())
    with patch.dict("sys.modules", {"strands.models.openai": MagicMock(OpenAIModel=mock_cls)}):
        m = _reload_model_module(monkeypatch, "openai", api_key="sk-o")
        m._build_model()
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["client_args"]["api_key"] == "sk-o"


def test_build_model_unknown_backend_falls_back_to_anthropic(monkeypatch):
    mock_cls = MagicMock(return_value=MagicMock())
    with patch.dict(
        "sys.modules", {"strands.models.anthropic": MagicMock(AnthropicModel=mock_cls)}
    ):
        m = _reload_model_module(monkeypatch, "notabackend")
        m._build_model()
    mock_cls.assert_called_once()


def test_get_model_caches(monkeypatch):
    mock_cls = MagicMock(return_value=MagicMock())
    with patch.dict(
        "sys.modules", {"strands.models.anthropic": MagicMock(AnthropicModel=mock_cls)}
    ):
        m = _reload_model_module(monkeypatch, "anthropic", api_key="sk-x")
        first = m.get_model()
        second = m.get_model()
    assert first is second
    assert mock_cls.call_count == 1
