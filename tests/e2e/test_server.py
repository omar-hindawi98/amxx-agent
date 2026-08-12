"""
End-to-end tests for the TCP server.

These tests start a real asyncio TCP server with the handle() coroutine
but replace the Strands Agent with a mock, so no Claude API key is needed.
"""

import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


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


def _mem():
    import amxmodx_genai.core.memory as m

    return m


async def tcp_exchange(host: str, port: int, msg: dict) -> list[dict]:
    """Send one JSON message; read all response frames until type=done."""
    reader, writer = await asyncio.open_connection(host, port)
    writer.write((json.dumps(msg) + "\n").encode())
    await writer.drain()

    frames: list[dict] = []
    while True:
        raw = await asyncio.wait_for(reader.readline(), timeout=5.0)
        if not raw:
            break
        frame = json.loads(raw.decode())
        frames.append(frame)
        if frame.get("type") == "done":
            break

    writer.close()
    await writer.wait_closed()
    return frames


def make_agent_result(text: str) -> MagicMock:
    block = MagicMock()
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    result = MagicMock()
    result.message = msg
    return result


def _get_handle():
    from amxmodx_genai.core.handler import handle

    return handle


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_memory(unused_tcp_port):
    mem = _mem()
    mem.update("3", "hello", "world")
    assert mem.get("3") != []

    srv = await asyncio.start_server(_get_handle(), "127.0.0.1", unused_tcp_port)
    async with srv:
        reader, writer = await asyncio.open_connection("127.0.0.1", unused_tcp_port)
        writer.write(
            (json.dumps({"type": "clear_memory", "player": 3, "session_id": "3"}) + "\n").encode()
        )
        await writer.drain()
        data = await asyncio.wait_for(reader.read(1), timeout=2.0)
        assert data == b""
        writer.close()

    assert mem.get("3") == []


@pytest.mark.asyncio
async def test_clear_memory_defaults_to_player_string(unused_tcp_port):
    mem = _mem()
    mem.update("3", "hello", "world")

    srv = await asyncio.start_server(_get_handle(), "127.0.0.1", unused_tcp_port)
    async with srv:
        reader, writer = await asyncio.open_connection("127.0.0.1", unused_tcp_port)
        writer.write((json.dumps({"type": "clear_memory", "player": 3}) + "\n").encode())
        await writer.drain()
        await asyncio.wait_for(reader.read(1), timeout=2.0)
        writer.close()

    assert mem.get("3") == []


@pytest.mark.asyncio
async def test_empty_prompt_returns_error(unused_tcp_port):
    srv = await asyncio.start_server(_get_handle(), "127.0.0.1", unused_tcp_port)
    async with srv:
        frames = await tcp_exchange(
            "127.0.0.1",
            unused_tcp_port,
            {"type": "query", "player": 1, "prompt": "   ", "tools": []},
        )

    types = [f["type"] for f in frames]
    assert "response" in types
    assert "done" in types


@pytest.mark.asyncio
async def test_query_response_and_done(unused_tcp_port):
    agent_result = make_agent_result("Buy AK47 and vesthelm.")

    with patch("amxmodx_genai.core.handler.Agent") as MockAgent:
        mock_instance = MagicMock()
        mock_instance.invoke_async = AsyncMock(return_value=agent_result)
        MockAgent.return_value = mock_instance

        srv = await asyncio.start_server(_get_handle(), "127.0.0.1", unused_tcp_port)
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
    assert "AK47" in response["text"]


@pytest.mark.asyncio
async def test_memory_updated_after_query(unused_tcp_port):
    agent_result = make_agent_result("Save this round.")

    with patch("amxmodx_genai.core.handler.Agent") as MockAgent:
        mock_instance = MagicMock()
        mock_instance.invoke_async = AsyncMock(return_value=agent_result)
        MockAgent.return_value = mock_instance

        srv = await asyncio.start_server(_get_handle(), "127.0.0.1", unused_tcp_port)
        async with srv:
            await tcp_exchange(
                "127.0.0.1",
                unused_tcp_port,
                {"type": "query", "player": 5, "prompt": "should I save?", "tools": []},
            )

    h = _mem().get("5")  # default session_id = str(player)
    assert len(h) == 2
    assert h[0]["role"] == "user"
    assert h[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_named_session_memory(unused_tcp_port):
    agent_result = make_agent_result("Focus B site.")

    with patch("amxmodx_genai.core.handler.Agent") as MockAgent:
        mock_instance = MagicMock()
        mock_instance.invoke_async = AsyncMock(return_value=agent_result)
        MockAgent.return_value = mock_instance

        srv = await asyncio.start_server(_get_handle(), "127.0.0.1", unused_tcp_port)
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
    assert _mem().get("1") == []  # player session untouched


@pytest.mark.asyncio
async def test_longterm_summary_stored_on_clear(unused_tcp_port):
    mem = _mem()
    # Seed short-term memory directly.
    mem.update("7", "what gun to buy?", "Buy AK47.")

    summary_result = make_agent_result("- Prefers AK47")

    with patch("amxmodx_genai.core.handler.Agent") as MockAgent:
        mock_instance = MagicMock()
        mock_instance.invoke_async = AsyncMock(return_value=summary_result)
        MockAgent.return_value = mock_instance

        srv = await asyncio.start_server(_get_handle(), "127.0.0.1", unused_tcp_port)
        async with srv:
            reader, writer = await asyncio.open_connection("127.0.0.1", unused_tcp_port)
            writer.write(
                (
                    json.dumps({"type": "clear_memory", "player": 7, "session_id": "7"}) + "\n"
                ).encode()
            )
            await writer.drain()
            await asyncio.wait_for(reader.read(1), timeout=2.0)
            writer.close()

    assert mem.get("7") == []
    assert mem.get_longterm("7") != ""


@pytest.mark.asyncio
async def test_longterm_injected_into_system_prompt(unused_tcp_port):
    mem = _mem()
    mem.set_longterm("8", "- Player prefers rifles")

    agent_result = make_agent_result("Buy AK47.")
    captured_kwargs: dict = {}

    def capture_agent(*args, **kwargs):
        captured_kwargs.update(kwargs)
        inst = MagicMock()
        inst.invoke_async = AsyncMock(return_value=agent_result)
        return inst

    with patch("amxmodx_genai.core.handler.Agent", side_effect=capture_agent):
        srv = await asyncio.start_server(_get_handle(), "127.0.0.1", unused_tcp_port)
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

    assert "Player prefers rifles" in captured_kwargs.get("system_prompt", "")
