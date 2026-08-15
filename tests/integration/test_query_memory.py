"""
Tests for the core query/response/memory flow.

Uses a real asyncio TCP server with the handle() coroutine but mocks the
Strands Agent, so no Claude API key is needed.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.integration.conftest import requires_ollama
from tests.integration.helpers import get_handle, make_agent_result, tcp_exchange


def _mem():
    import amxx_agent.core.memory as m

    return m


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@requires_ollama
@pytest.mark.asyncio
async def test_clear_memory(unused_tcp_port):
    mem = _mem()
    mem.update("3", "hello", "world")
    assert mem.get("3") != []

    srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
    async with srv:
        reader, writer = await asyncio.open_connection("127.0.0.1", unused_tcp_port)
        writer.write(
            (
                json.dumps({"type": "clear_memory", "player": 3, "session_id": "3"})
                + "\n"
            ).encode()
        )
        await writer.drain()
        await asyncio.wait_for(reader.readline(), timeout=70.0)
        writer.close()
        await writer.wait_closed()

    assert mem.get("3") == []


@requires_ollama
@pytest.mark.asyncio
async def test_clear_memory_defaults_to_server_when_no_session_id(unused_tcp_port):
    mem = _mem()
    mem.update("server", "hello", "world")

    srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
    async with srv:
        reader, writer = await asyncio.open_connection("127.0.0.1", unused_tcp_port)
        writer.write(
            (json.dumps({"type": "clear_memory", "player": 0}) + "\n").encode()
        )
        await writer.drain()
        await asyncio.wait_for(reader.readline(), timeout=70.0)
        writer.close()
        await writer.wait_closed()

    assert mem.get("server") == []


@pytest.mark.asyncio
async def test_empty_prompt_returns_error(unused_tcp_port):
    srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
    async with srv:
        frames = await tcp_exchange(
            "127.0.0.1",
            unused_tcp_port,
            {"type": "query", "player": 1, "prompt": "   ", "tools": []},
        )

    types = [f["type"] for f in frames]
    assert "response" in types
    assert "done" in types


@requires_ollama
@pytest.mark.asyncio
async def test_query_response_and_done(unused_tcp_port):
    srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
    async with srv:
        frames = await tcp_exchange(
            "127.0.0.1",
            unused_tcp_port,
            {"type": "query", "player": 2, "prompt": "what to buy?", "tools": []},
        )

    types = [f["type"] for f in frames]
    assert "response" in types
    assert "done" in types
    response = next(f for f in frames if f["type"] == "response")
    assert response["text"].strip()


@requires_ollama
@pytest.mark.asyncio
async def test_memory_updated_after_query(unused_tcp_port):
    srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
    async with srv:
        await tcp_exchange(
            "127.0.0.1",
            unused_tcp_port,
            {"type": "query", "player": 5, "prompt": "should I save?", "tools": []},
        )

    h = _mem().get("server")
    assert len(h) == 2
    assert h[0]["role"] == "user"
    assert h[1]["role"] == "assistant"


@requires_ollama
@pytest.mark.asyncio
async def test_named_session_memory(unused_tcp_port):
    srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
    async with srv:
        await tcp_exchange(
            "127.0.0.1",
            unused_tcp_port,
            {
                "type": "query",
                "player": 1,
                "session_id": "ct_team",
                "prompt": "what is our strategy?",
                "tools": [],
            },
        )

    assert _mem().get("ct_team") != []
    assert _mem().get("1") == []


@pytest.mark.asyncio
async def test_longterm_summary_stored_on_clear(unused_tcp_port):
    mem = _mem()
    mem.update("7", "what gun to buy?", "Buy AK47.")

    with patch(
        "amxx_agent.core.handler.summarize_session",
        new=AsyncMock(return_value="- Prefers AK47"),
    ):
        srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
        async with srv:
            reader, writer = await asyncio.open_connection("127.0.0.1", unused_tcp_port)
            writer.write(
                (
                    json.dumps({"type": "clear_memory", "player": 7, "session_id": "7"})
                    + "\n"
                ).encode()
            )
            await writer.drain()
            await asyncio.wait_for(reader.readline(), timeout=70.0)
            writer.close()
            await writer.wait_closed()

    assert mem.get("7") == []
    assert mem.get_longterm("7") == "- Prefers AK47"


@pytest.mark.asyncio
async def test_longterm_injected_into_system_prompt(unused_tcp_port):
    mem = _mem()
    mem.set_longterm("8", "- Player prefers rifles")

    captured_kwargs: dict = {}

    def capture_agent(*args, **kwargs):
        captured_kwargs.update(kwargs)
        inst = MagicMock()
        inst.invoke_async = AsyncMock(return_value=make_agent_result("Buy AK47."))
        return inst

    with patch("amxx_agent.core.handler.Agent", side_effect=capture_agent):
        srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
        async with srv:
            await tcp_exchange(
                "127.0.0.1",
                unused_tcp_port,
                {
                    "type": "query",
                    "player": 8,
                    "session_id": "8",
                    "prompt": "buy advice",
                    "tools": [],
                },
            )

    system_prompt = captured_kwargs.get("system_prompt", [])
    prompt_text = (
        "".join(b.get("text", "") for b in system_prompt)
        if isinstance(system_prompt, list)
        else system_prompt
    )
    assert "Player prefers rifles" in prompt_text
