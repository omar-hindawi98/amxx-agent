"""Model factory - returns the right Strands model based on GENAI_MODEL_BACKEND."""

from amxmodx_genai.config import settings

_SUPPORTED = ("anthropic", "bedrock", "ollama", "litellm", "openai")
_OLLAMA_DEFAULT_ENDPOINT = "http://localhost:11434"
_NEEDS_API_KEY = frozenset({"anthropic", "openai", "litellm"})

_cached_model = None
_cached_summary_model = None


def validate() -> None:
    """Raise at startup if required credentials for the configured backend are missing."""
    backend = settings.model_backend
    if backend in _NEEDS_API_KEY and not settings.model_api_key:
        raise RuntimeError(f"GENAI_MODEL_API_KEY is required when GENAI_MODEL_BACKEND={backend}")


def get_model():
    """Return the cached Strands model, constructing it on first call."""
    global _cached_model
    if _cached_model is None:
        _cached_model = _build_model()
    return _cached_model


def get_summary_model():
    """Return a cached model for summarization with a higher token ceiling.

    Summarization prompts can be large (full conversation history), so the
    output budget must be at least 1024 tokens regardless of GENAI_MODEL_TOKENS.
    """
    global _cached_summary_model
    if _cached_summary_model is None:
        _cached_summary_model = _build_model(max_tokens=max(settings.model_tokens, 1024))
    return _cached_summary_model


def _build_model(max_tokens: int | None = None):
    """Construct a new Strands model for the configured backend.

    Supported backends (GENAI_MODEL_BACKEND):
      anthropic - Anthropic API (default); requires GENAI_MODEL_API_KEY
      bedrock   - AWS Bedrock; credentials via standard AWS env vars
      ollama    - local Ollama server; set GENAI_MODEL_ENDPOINT for a non-default host
      litellm   - LiteLLM proxy; covers OpenRouter, Groq, Cohere, etc.
      openai    - OpenAI-compatible API; set GENAI_MODEL_ENDPOINT for a custom base URL
    """
    backend = settings.model_backend
    model_id = settings.model_name
    if max_tokens is None:
        max_tokens = settings.model_tokens
    endpoint = settings.model_endpoint
    api_key = settings.model_api_key

    if backend == "bedrock":
        from strands.models.bedrock import BedrockModel

        return BedrockModel(model_id=model_id, max_tokens=max_tokens)

    if backend == "ollama":
        from strands.models.ollama import OllamaModel

        return OllamaModel(
            host=endpoint or _OLLAMA_DEFAULT_ENDPOINT,
            model_id=model_id,
            max_tokens=max_tokens,
        )

    if backend == "litellm":
        from strands.models.litellm import LiteLLMModel

        client_args: dict = {"api_key": api_key} if api_key else {}
        if endpoint:
            client_args["base_url"] = endpoint
        return LiteLLMModel(
            model_id=model_id, params={"max_tokens": max_tokens}, client_args=client_args
        )

    if backend == "openai":
        from strands.models.openai import OpenAIModel

        client_args = {"api_key": api_key} if api_key else {}
        if endpoint:
            client_args["base_url"] = endpoint
        return OpenAIModel(
            model_id=model_id, params={"max_tokens": max_tokens}, client_args=client_args
        )

    if backend != "anthropic":
        import logging

        logging.getLogger(__name__).warning(
            "unknown backend %r, falling back to anthropic (supported: %s)",
            backend,
            ", ".join(_SUPPORTED),
        )

    from strands.models.anthropic import AnthropicModel

    client_args = {"api_key": api_key} if api_key else {}
    return AnthropicModel(model_id=model_id, max_tokens=max_tokens, client_args=client_args)
