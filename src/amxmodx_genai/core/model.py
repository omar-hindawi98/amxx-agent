"""Model factory - returns the right Strands model based on GENAI_BACKEND."""

from amxmodx_genai.config import BACKEND, MODEL, OLLAMA_HOST, OLLAMA_MODEL, TOKENS


def make_model():
    if BACKEND == "ollama":
        from strands.models.ollama import OllamaModel

        return OllamaModel(host=OLLAMA_HOST, model_id=OLLAMA_MODEL)
    from strands.models.anthropic import AnthropicModel

    return AnthropicModel(model_id=MODEL, max_tokens=TOKENS)
