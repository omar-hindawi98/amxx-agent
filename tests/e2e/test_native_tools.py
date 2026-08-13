"""Tests for native sidecar tools wired into the Agent."""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.e2e.conftest import get_handle, make_agent_result, tcp_exchange


@pytest.mark.asyncio
async def test_native_tools_passed_to_agent(unused_tcp_port):
    """native_tools list is included in Agent kwargs for non-ollama backends."""
    captured_kwargs: dict = {}

    def capture_agent(**kwargs):
        captured_kwargs.update(kwargs)
        inst = MagicMock()
        inst.invoke_async = AsyncMock(return_value=make_agent_result("ok"))
        return inst

    with patch("amxmodx_genai.core.handler.Agent", side_effect=capture_agent):
        srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
        async with srv:
            await tcp_exchange(
                "127.0.0.1",
                unused_tcp_port,
                {"type": "query", "player": 1, "prompt": "what time is it?", "tools": []},
            )

    tool_names = [t.__name__ for t in captured_kwargs.get("tools", [])]
    assert "current_datetime" in tool_names


@pytest.mark.asyncio
async def test_current_datetime_tool_callable_returns_iso_string(unused_tcp_port):
    """current_datetime tool can be called and returns an ISO 8601 string."""
    call_result: list[str] = []
    captured_tools: list = []

    async def fake_invoke(prompt):
        for t in captured_tools:
            if t.__name__ == "current_datetime":
                call_result.append(t())
                break
        return make_agent_result("It is now some time.")

    def capture_agent(**kwargs):
        captured_tools.extend(kwargs.get("tools", []))
        inst = MagicMock()
        inst.invoke_async = AsyncMock(side_effect=fake_invoke)
        return inst

    with patch("amxmodx_genai.core.handler.Agent", side_effect=capture_agent):
        srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
        async with srv:
            await tcp_exchange(
                "127.0.0.1",
                unused_tcp_port,
                {"type": "query", "player": 1, "prompt": "what time is it?", "tools": []},
            )

    assert len(call_result) == 1
    assert "T" in call_result[0]  # ISO 8601: "2024-01-15T10:30:00"


@pytest.mark.asyncio
async def test_native_tools_omitted_for_ollama(unused_tcp_port, monkeypatch):
    """Native tools are excluded from Agent kwargs when backend is ollama."""
    monkeypatch.setenv("GENAI_MODEL_BACKEND", "ollama")
    for mod in list(sys.modules):
        if mod.startswith("amxmodx_genai"):
            del sys.modules[mod]

    captured_kwargs: dict = {}

    def capture_agent(**kwargs):
        captured_kwargs.update(kwargs)
        inst = MagicMock()
        inst.invoke_async = AsyncMock(return_value=make_agent_result("ok"))
        return inst

    with patch("amxmodx_genai.core.handler.Agent", side_effect=capture_agent):
        srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
        async with srv:
            await tcp_exchange(
                "127.0.0.1",
                unused_tcp_port,
                {"type": "query", "player": 1, "prompt": "hello", "tools": []},
            )

    tool_names = [t.__name__ for t in captured_kwargs.get("tools", [])]
    assert "current_datetime" not in tool_names
