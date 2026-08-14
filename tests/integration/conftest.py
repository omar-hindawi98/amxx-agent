"""Pytest configuration and shared fixtures for integration tests."""

import os
import sys
import urllib.request

import pytest

from tests.integration.helpers import (
    get_handle,
    make_agent_factory,
    make_agent_result,
    tcp_exchange,
)

__all__ = ["get_handle", "make_agent_factory", "make_agent_result", "tcp_exchange"]

_OLLAMA_ENDPOINT = os.environ.get("GENAI_MODEL_ENDPOINT", "http://localhost:11434")
_OLLAMA_MODEL = os.environ.get("GENAI_MODEL_NAME", "llama3.2:1b")


def _ollama_reachable() -> bool:
    try:
        urllib.request.urlopen(f"{_OLLAMA_ENDPOINT}/api/tags", timeout=2)
        return True
    except Exception:
        return False


_ollama_available: bool = _ollama_reachable()

requires_ollama = pytest.mark.skipif(
    not _ollama_available,
    reason=f"Ollama not reachable at {_OLLAMA_ENDPOINT}",
)


@pytest.fixture(autouse=True)
def fresh_memory(tmp_path):
    db_file = str(tmp_path / "integration_memory.db")
    os.environ["GENAI_MEMORY_PATH"] = db_file
    if _ollama_available:
        os.environ["GENAI_MODEL_BACKEND"] = "ollama"
        os.environ["GENAI_MODEL_NAME"] = _OLLAMA_MODEL
        os.environ["GENAI_MODEL_ENDPOINT"] = _OLLAMA_ENDPOINT
    for mod in list(sys.modules):
        if mod.startswith("amxmodx_genai"):
            del sys.modules[mod]
    yield
    del os.environ["GENAI_MEMORY_PATH"]
    os.environ.pop("GENAI_MODEL_BACKEND", None)
    os.environ.pop("GENAI_MODEL_NAME", None)
    os.environ.pop("GENAI_MODEL_ENDPOINT", None)
    for mod in list(sys.modules):
        if mod.startswith("amxmodx_genai"):
            del sys.modules[mod]
