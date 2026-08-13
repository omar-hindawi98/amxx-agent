"""Tests for plugin tool round-trips between the handler and game server."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.integration.helpers import get_handle, make_agent_result, tcp_exchange


@pytest.mark.asyncio
async def test_plugin_tool_registered_in_agent_kwargs(unused_tcp_port):
    """Tools sent in the query message are passed to the Agent."""
    captured_tools: list = []

    async def fake_invoke(prompt):
        tool_fn = [t for t in captured_tools if t.__name__ == "get_player_info"][0]
        await tool_fn(player_id=1)
        return make_agent_result("Player has 100 health.")

    def capture_agent(**kwargs):
        captured_tools.extend(kwargs.get("tools", []))
        inst = MagicMock()
        inst.invoke_async = AsyncMock(side_effect=fake_invoke)
        return inst

    async def mock_call(name, args, send, tool_result_queue, request_id, session_data):
        session_data.setdefault("calls", []).append(
            {"tool": name, "args": args, "result": '{"health":100}'}
        )
        return '{"health":100}'

    with (
        patch("amxmodx_genai.core.handler.Agent", side_effect=capture_agent),
        patch("amxmodx_genai.tools.plugin._call", side_effect=mock_call),
    ):
        srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
        async with srv:
            frames = await tcp_exchange(
                "127.0.0.1",
                unused_tcp_port,
                {
                    "type": "query",
                    "player": 1,
                    "prompt": "what is player 1 health?",
                    "tools": [
                        {
                            "name": "get_player_info",
                            "description": "Returns player info.",
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
            )

    types = [f["type"] for f in frames]
    assert "response" in types
    assert "done" in types
    assert "get_player_info" in [t.__name__ for t in captured_tools]


@pytest.mark.asyncio
async def test_plugin_tool_result_reaches_agent(unused_tcp_port):
    """Tool result returned by _call is received by the agent invocation."""
    tool_return = '{"name":"Alice","health":80}'
    call_log: list[str] = []

    async def mock_call(name, args, send, tool_result_queue, request_id, session_data):
        call_log.append(name)
        session_data.setdefault("calls", []).append(
            {"tool": name, "args": args, "result": tool_return}
        )
        return tool_return

    captured_tools: list = []

    async def fake_invoke(prompt):
        tool_fn = [t for t in captured_tools if t.__name__ == "get_player_info"][0]
        result = await tool_fn(player_id=1)
        assert result == tool_return
        return make_agent_result("Alice has 80 health.")

    def capture_agent(**kwargs):
        captured_tools.extend(kwargs.get("tools", []))
        inst = MagicMock()
        inst.invoke_async = AsyncMock(side_effect=fake_invoke)
        return inst

    with (
        patch("amxmodx_genai.core.handler.Agent", side_effect=capture_agent),
        patch("amxmodx_genai.tools.plugin._call", side_effect=mock_call),
    ):
        srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
        async with srv:
            frames = await tcp_exchange(
                "127.0.0.1",
                unused_tcp_port,
                {
                    "type": "query",
                    "player": 2,
                    "prompt": "describe player 1",
                    "tools": [
                        {
                            "name": "get_player_info",
                            "description": "Returns player info.",
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
            )

    assert "get_player_info" in call_log
    response = next(f for f in frames if f["type"] == "response")
    assert "Alice" in response["text"]


@pytest.mark.asyncio
async def test_plugin_tool_calls_recorded_in_session_data(unused_tcp_port):
    """session_data.calls is populated after tool invocations."""
    captured_session_data: dict = {}

    async def mock_call(name, args, send, tool_result_queue, request_id, session_data):
        session_data.setdefault("calls", []).append({"tool": name, "args": args, "result": "ok"})
        captured_session_data.update(session_data)
        return "ok"

    captured_tools: list = []

    async def fake_invoke(prompt):
        await captured_tools[0](player_id=3)
        return make_agent_result("Done.")

    def capture_agent(**kwargs):
        captured_tools.extend(kwargs.get("tools", []))
        inst = MagicMock()
        inst.invoke_async = AsyncMock(side_effect=fake_invoke)
        return inst

    with (
        patch("amxmodx_genai.core.handler.Agent", side_effect=capture_agent),
        patch("amxmodx_genai.tools.plugin._call", side_effect=mock_call),
    ):
        srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
        async with srv:
            await tcp_exchange(
                "127.0.0.1",
                unused_tcp_port,
                {
                    "type": "query",
                    "player": 3,
                    "prompt": "kick idle players",
                    "tools": [
                        {
                            "name": "kick_player",
                            "description": "Kicks a player.",
                            "params": [
                                {
                                    "name": "player_id",
                                    "type": "integer",
                                    "required": True,
                                    "description": "index",
                                }
                            ],
                        }
                    ],
                },
            )

    assert len(captured_session_data.get("calls", [])) == 1
    assert captured_session_data["calls"][0]["tool"] == "kick_player"
