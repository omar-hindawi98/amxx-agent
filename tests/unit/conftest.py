"""Pytest configuration for unit tests.

Provides fresh_memory - mirrors the fixture in tests/e2e/conftest.py so that
server-level tests moved from tests/e2e/ keep working without modification.
"""

import os
import sys

import pytest


@pytest.fixture(autouse=True)
def fresh_memory(tmp_path):
    db_file = str(tmp_path / "unit_memory.db")
    os.environ["AGENT_MEMORY_PATH"] = db_file
    for mod in list(sys.modules):
        if mod.startswith("amxx_agent"):
            del sys.modules[mod]
    yield
    del os.environ["AGENT_MEMORY_PATH"]
    for mod in list(sys.modules):
        if mod.startswith("amxx_agent"):
            del sys.modules[mod]
