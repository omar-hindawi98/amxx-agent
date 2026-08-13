"""Pytest configuration and shared fixtures for e2e tests."""

import os
import sys

import pytest

from tests.e2e.helpers import get_handle, make_agent_factory, make_agent_result, tcp_exchange

__all__ = ["get_handle", "make_agent_factory", "make_agent_result", "tcp_exchange"]


@pytest.fixture(autouse=True)
def fresh_memory(tmp_path):
    db_file = str(tmp_path / "e2e_memory.db")
    os.environ["GENAI_MEMORY_PATH"] = db_file
    for mod in list(sys.modules):
        if mod.startswith("amxmodx_genai"):
            del sys.modules[mod]
    yield
    del os.environ["GENAI_MEMORY_PATH"]
    for mod in list(sys.modules):
        if mod.startswith("amxmodx_genai"):
            del sys.modules[mod]
