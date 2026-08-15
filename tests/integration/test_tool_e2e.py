"""End-to-end tool tests: real _call, no mock, tool_call/tool_result over TCP.

These tests exercise the full path: Agent calls tool -> _call sends tool_call
frame over TCP -> client (acting as AMXMODX plugin) sends tool_result back ->
_call returns the result to the Agent. No mocking of _call or the queue.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.integration.helpers import make_agent_result


def _get_persistent():
    import amxx_agent.server as srv_mod
    from amxx_agent.server import _handle_persistent

    if srv_mod._sem is None:
        srv_mod._sem = asyncio.Semaphore(8)
    return _handle_persistent


async def _run_with_tool_responses(
    port: int,
    query: dict,
    tool_responses: dict[str, str],
) -> list[dict]:
    """Send a query and respond to any tool_call frames as a plugin would.

    tool_responses: maps tool name -> content string to return.
    Returns all frames received until done.
    """
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write((json.dumps(query) + "\n").encode())
    await writer.drain()

    all_frames: list[dict] = []
    request_id = query.get("request_id", "")
    while True:
        raw = await asyncio.wait_for(reader.readline(), timeout=5.0)
        frame = json.loads(raw.decode())
        all_frames.append(frame)
        if frame.get("type") == "tool_call" and frame.get("request_id") == request_id:
            content = tool_responses.get(frame.get("name", ""), "(unknown tool)")
            writer.write(
                (
                    json.dumps(
                        {
                            "type": "tool_result",
                            "request_id": request_id,
                            "id": frame["id"],
                            "content": content,
                        }
                    )
                    + "\n"
                ).encode()
            )
            await writer.drain()
        if frame.get("type") == "done" and frame.get("request_id") == request_id:
            break

    writer.close()
    await writer.wait_closed()
    return all_frames


# ---------------------------------------------------------------------------
# Single tool: full wire roundtrip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_real_tool_roundtrip_over_wire(unused_tcp_port):
    """_call sends tool_call frame, plugin responds via TCP, _call returns the result to Agent."""
    agent_received: list[str] = []

    def make_agent(**kwargs):
        inst = MagicMock()

        async def fake_invoke(prompt):
            tool_fns = {t.__name__: t for t in kwargs.get("tools", [])}
            result = await tool_fns["get_health"](player_id=1)
            agent_received.append(result)
            return make_agent_result(f"health:{result}")

        inst.invoke_async = AsyncMock(side_effect=fake_invoke)
        return inst

    with patch("amxx_agent.core.handler.Agent", side_effect=make_agent):
        srv = await asyncio.start_server(_get_persistent(), "127.0.0.1", unused_tcp_port)
        async with srv:
            frames = await _run_with_tool_responses(
                unused_tcp_port,
                {
                    "type": "query",
                    "request_id": "r1",
                    "player": 1,
                    "prompt": "what is health?",
                    "tools": [
                        {
                            "name": "get_health",
                            "description": "returns player health",
                            "params": [
                                {
                                    "name": "player_id",
                                    "type": "integer",
                                    "required": True,
                                    "description": "player index",
                                }
                            ],
                        }
                    ],
                },
                {"get_health": '{"health": 100}'},
            )

    assert agent_received == ['{"health": 100}']
    response = next(f for f in frames if f["type"] == "response")
    assert '{"health": 100}' in response["text"]


# ---------------------------------------------------------------------------
# Two tools called sequentially in the same request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_tools_called_sequentially(unused_tcp_port):
    """Agent calling two tools back-to-back both complete with correct results."""
    agent_received: list[str] = []

    def make_agent(**kwargs):
        inst = MagicMock()

        async def fake_invoke(prompt):
            tool_fns = {t.__name__: t for t in kwargs.get("tools", [])}
            r_a = await tool_fns["tool_a"](x=1)
            r_b = await tool_fns["tool_b"](y=2)
            agent_received.extend([r_a, r_b])
            return make_agent_result(f"{r_a}|{r_b}")

        inst.invoke_async = AsyncMock(side_effect=fake_invoke)
        return inst

    with patch("amxx_agent.core.handler.Agent", side_effect=make_agent):
        srv = await asyncio.start_server(_get_persistent(), "127.0.0.1", unused_tcp_port)
        async with srv:
            frames = await _run_with_tool_responses(
                unused_tcp_port,
                {
                    "type": "query",
                    "request_id": "r1",
                    "player": 1,
                    "prompt": "call both tools",
                    "tools": [
                        {
                            "name": "tool_a",
                            "description": "tool a",
                            "params": [
                                {
                                    "name": "x",
                                    "type": "integer",
                                    "required": True,
                                    "description": "x",
                                }
                            ],
                        },
                        {
                            "name": "tool_b",
                            "description": "tool b",
                            "params": [
                                {
                                    "name": "y",
                                    "type": "integer",
                                    "required": True,
                                    "description": "y",
                                }
                            ],
                        },
                    ],
                },
                {"tool_a": "result_a", "tool_b": "result_b"},
            )

    assert agent_received == ["result_a", "result_b"]
    response = next(f for f in frames if f["type"] == "response")
    assert "result_a" in response["text"]
    assert "result_b" in response["text"]


# ---------------------------------------------------------------------------
# Tool result truncation at _MAX_TOOL_RESULT_BYTES
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_result_truncated_at_limit(unused_tcp_port):
    """Tool results larger than _MAX_TOOL_RESULT_BYTES are truncated before reaching the Agent."""
    from amxx_agent.tools.plugin import _MAX_TOOL_RESULT_BYTES

    large_payload = "Z" * (_MAX_TOOL_RESULT_BYTES + 500)
    agent_received: list[str] = []

    def make_agent(**kwargs):
        inst = MagicMock()

        async def fake_invoke(prompt):
            tool_fns = {t.__name__: t for t in kwargs.get("tools", [])}
            result = await tool_fns["big_tool"]()
            agent_received.append(result)
            return make_agent_result("got it")

        inst.invoke_async = AsyncMock(side_effect=fake_invoke)
        return inst

    with patch("amxx_agent.core.handler.Agent", side_effect=make_agent):
        srv = await asyncio.start_server(_get_persistent(), "127.0.0.1", unused_tcp_port)
        async with srv:
            await _run_with_tool_responses(
                unused_tcp_port,
                {
                    "type": "query",
                    "request_id": "r1",
                    "player": 1,
                    "prompt": "call big tool",
                    "tools": [{"name": "big_tool", "description": "returns large payload"}],
                },
                {"big_tool": large_payload},
            )

    assert len(agent_received) == 1
    assert len(agent_received[0]) == _MAX_TOOL_RESULT_BYTES
    assert agent_received[0] == "Z" * _MAX_TOOL_RESULT_BYTES


# ---------------------------------------------------------------------------
# Tool result is recorded in memory after query
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_call_result_stored_in_memory(unused_tcp_port):
    """After a query with a tool call, the exchange is written to memory."""
    import amxx_agent.core.memory as mem

    def make_agent(**kwargs):
        inst = MagicMock()

        async def fake_invoke(prompt):
            tool_fns = {t.__name__: t for t in kwargs.get("tools", [])}
            await tool_fns["ping"]()
            return make_agent_result("pong received")

        inst.invoke_async = AsyncMock(side_effect=fake_invoke)
        return inst

    with patch("amxx_agent.core.handler.Agent", side_effect=make_agent):
        srv = await asyncio.start_server(_get_persistent(), "127.0.0.1", unused_tcp_port)
        async with srv:
            await _run_with_tool_responses(
                unused_tcp_port,
                {
                    "type": "query",
                    "request_id": "r1",
                    "player": 1,
                    "session_id": "mem_test",
                    "prompt": "ping the server",
                    "tools": [{"name": "ping", "description": "sends a ping"}],
                },
                {"ping": "pong"},
            )

    history = mem.get("mem_test")
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"
    assert any("pong received" in str(b) for b in history[1]["content"])
