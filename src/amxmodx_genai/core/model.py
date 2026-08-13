"""Model factory - returns the right Strands model based on GENAI_MODEL_BACKEND."""

from amxmodx_genai.config import settings

_SUPPORTED = ("anthropic", "bedrock", "ollama", "litellm", "openai")

_OLLAMA_DEFAULT_ENDPOINT = "http://localhost:11434"


def make_model():
    """Return a Strands model for the configured backend.

    Supported backends (GENAI_MODEL_BACKEND):
      anthropic - Anthropic API (default)
      bedrock   - AWS Bedrock; credentials via standard AWS env vars
      ollama    - local Ollama server; set GENAI_MODEL_ENDPOINT for a non-default host
      litellm   - LiteLLM proxy; covers OpenRouter, Groq, Cohere, etc.
      openai    - OpenAI-compatible API; set GENAI_MODEL_ENDPOINT for a custom base URL
    """
    backend = settings.model_backend
    model_id = settings.model_name
    max_tokens = settings.model_tokens
    endpoint = settings.model_endpoint

    if backend == "bedrock":
        from strands.models.bedrock import BedrockModel
        return BedrockModel(model_id=model_id, max_tokens=max_tokens)

    if backend == "ollama":
        from strands.models.ollama import OllamaModel
        return OllamaModel(host=endpoint or _OLLAMA_DEFAULT_ENDPOINT, model_id=model_id)

    if backend == "litellm":
        from strands.models.litellm import LiteLLMModel
        client_args = {"base_url": endpoint} if endpoint else {}
        return LiteLLMModel(model_id=model_id, params={"max_tokens": max_tokens}, client_args=client_args)

    if backend == "openai":
        from strands.models.openai import OpenAIModel
        client_args = {"base_url": endpoint} if endpoint else {}
        return OpenAIModel(model_id=model_id, params={"max_tokens": max_tokens}, client_args=client_args)

    if backend != "anthropic":
        import logging
        logging.getLogger(__name__).warning(
            "unknown backend %r, falling back to anthropic (supported: %s)",
            backend,
            ", ".join(_SUPPORTED),
        )

    from strands.models.anthropic import AnthropicModel
    return AnthropicModel(model_id=model_id, max_tokens=max_tokens)
