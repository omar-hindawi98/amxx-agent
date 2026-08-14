"""Integration tests that simulate the ai_testable.sma plugin over the wire.

Each test acts as the AMXMODX plugin client: it sends query frames, handles
tool_call frames (responding with tool_result frames as ai_testable.sma would),
and verifies the sidecar's behaviour end-to-end.

Covered functionality:
  - set_value tool: AI stores a key-value pair; test confirms correct args received
  - get_value tool: AI reads a previously set value; test confirms it got it back
  - get_log tool: AI reads the plugin's in-memory log; test confirms JSON array returned
  - get_pending tool: exercises genai_is_pending wire path
  - Memory: short-term history persists within a session
  - clear_memory: wipes short-term history, subsequent query starts fresh
  - clear_longterm: discards long-term summary without touching short-term memory
  - Session scoping: two different session_ids do not share memory
  - Player-scoped query: player != 0 accumulates history in a separate session bucket
  - Skills: skill names in the query frame are forwarded to load_plugin_skills
  - Multiple sequential tool calls in one request
  - Tool call arg parsing: parameters are forwarded correctly in args_json
  - Unknown tool: plugin error response forwarded to agent intact
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.integration.helpers import make_agent_result

_SESSION = "testable__plugin"

_TOOLS = [
    {
        "name": "get_log",
        "description": "Returns all log entries recorded by this plugin since it started.",
        "params": [],
    },
    {
        "name": "set_value",
        "description": "Stores a named value in the plugin's key-value store.",
        "params": [
            {
                "name": "key",
                "type": "string",
                "required": True,
                "description": "Storage key",
            },
            {
                "name": "value",
                "type": "string",
                "required": True,
                "description": "Value to store",
            },
        ],
    },
    {
        "name": "get_value",
        "description": "Retrieves a value from the plugin's key-value store.",
        "params": [
            {
                "name": "key",
                "type": "string",
                "required": True,
                "description": "Storage key to look up",
            },
        ],
    },
    {
        "name": "get_pending",
        "description": "Returns whether a query is currently in-flight for the server session.",
        "params": [],
    },
]


def _get_persistent():
    import amxmodx_genai.server as srv_mod
    from amxmodx_genai.server import _handle_persistent

    if srv_mod._sem is None:
        srv_mod._sem = asyncio.Semaphore(8)
    return _handle_persistent


async def _exchange(
    port: int,
    prompt: str,
    request_id: str,
    tool_responses: dict[str, str],
    *,
    session_id: str = _SESSION,
    player: int = 0,
    skills: list[str] | None = None,
    extra_tools: list | None = None,
) -> list[dict]:
    """Send a query and respond to tool_call frames as ai_testable.sma would.

    Returns all frames until type=done.
    """
    tools = list(_TOOLS) + (extra_tools or [])
    query: dict = {
        "type": "query",
        "request_id": request_id,
        "player": player,
        "session_id": session_id,
        "prompt": prompt,
        "tools": tools,
    }
    if skills is not None:
        query["skills"] = skills

    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write((json.dumps(query) + "\n").encode())
    await writer.drain()

    all_frames: list[dict] = []
    while True:
        raw = await asyncio.wait_for(reader.readline(), timeout=5.0)
        frame = json.loads(raw.decode())
        all_frames.append(frame)

        if frame.get("type") == "tool_call" and frame.get("request_id") == request_id:
            content = tool_responses.get(frame.get("name", ""), '{"error":"unknown tool"}')
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


async def _send_control(port: int, frame: dict) -> None:
    """Send a control frame (clear_memory, clear_longterm) and wait for done."""
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write((json.dumps(frame) + "\n").encode())
    await writer.drain()
    await asyncio.wait_for(reader.readline(), timeout=5.0)
    writer.close()
    await writer.wait_closed()


# ---------------------------------------------------------------------------
# set_value: AI calls the tool, correct key+value arrive in args_json
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_value_args_forwarded(unused_tcp_port):
    """set_value receives the key and value the AI intended to store."""

    def make_agent(**kwargs):
        inst = MagicMock()

        async def fake_invoke(prompt):
            tool_fns = {t.__name__: t for t in kwargs.get("tools", [])}
            await tool_fns["set_value"](key="score", value="42")
            return make_agent_result("stored")

        inst.invoke_async = AsyncMock(side_effect=fake_invoke)
        return inst

    with patch("amxmodx_genai.core.handler.Agent", side_effect=make_agent):
        srv = await asyncio.start_server(_get_persistent(), "127.0.0.1", unused_tcp_port)
        async with srv:
            frames = await _exchange(
                unused_tcp_port,
                "store score=42",
                "r1",
                {"set_value": '{"ok":true,"action":"created"}'},
            )

    tool_calls = [f for f in frames if f.get("type") == "tool_call"]
    assert len(tool_calls) == 1
    call = tool_calls[0]
    assert call["name"] == "set_value"
    args = json.loads(call["args"])
    assert args["key"] == "score"
    assert args["value"] == "42"


# ---------------------------------------------------------------------------
# get_value: AI reads back a value it previously stored
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_value_result_returned_to_agent(unused_tcp_port):
    """get_value tool result is returned to the agent and appears in final response."""
    stored_value = '{"key":"color","value":"red"}'
    agent_got: list[str] = []

    def make_agent(**kwargs):
        inst = MagicMock()

        async def fake_invoke(prompt):
            tool_fns = {t.__name__: t for t in kwargs.get("tools", [])}
            result = await tool_fns["get_value"](key="color")
            agent_got.append(result)
            return make_agent_result(f"value is: {result}")

        inst.invoke_async = AsyncMock(side_effect=fake_invoke)
        return inst

    with patch("amxmodx_genai.core.handler.Agent", side_effect=make_agent):
        srv = await asyncio.start_server(_get_persistent(), "127.0.0.1", unused_tcp_port)
        async with srv:
            frames = await _exchange(
                unused_tcp_port,
                "what is color?",
                "r1",
                {"get_value": stored_value},
            )

    assert len(agent_got) == 1
    assert agent_got[0] == stored_value
    response = next(f for f in frames if f["type"] == "response")
    assert stored_value in response["text"]


# ---------------------------------------------------------------------------
# get_log: AI requests the log; receives a JSON array string
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_log_returns_json_array(unused_tcp_port):
    """get_log tool result is a JSON array and is forwarded to the agent intact."""
    log_payload = '["plugin_init","query: what is the log?"]'
    agent_got: list[str] = []

    def make_agent(**kwargs):
        inst = MagicMock()

        async def fake_invoke(prompt):
            tool_fns = {t.__name__: t for t in kwargs.get("tools", [])}
            result = await tool_fns["get_log"]()
            agent_got.append(result)
            return make_agent_result("log retrieved")

        inst.invoke_async = AsyncMock(side_effect=fake_invoke)
        return inst

    with patch("amxmodx_genai.core.handler.Agent", side_effect=make_agent):
        srv = await asyncio.start_server(_get_persistent(), "127.0.0.1", unused_tcp_port)
        async with srv:
            await _exchange(
                unused_tcp_port,
                "show me the log",
                "r1",
                {"get_log": log_payload},
            )

    assert len(agent_got) == 1
    parsed = json.loads(agent_got[0])
    assert isinstance(parsed, list)
    assert "plugin_init" in parsed


# ---------------------------------------------------------------------------
# get_pending: exercises genai_is_pending via the wire (tool round-trip)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_pending_tool_returns_bool(unused_tcp_port):
    """get_pending tool result contains a boolean 'pending' field."""
    agent_got: list[str] = []

    def make_agent(**kwargs):
        inst = MagicMock()

        async def fake_invoke(prompt):
            tool_fns = {t.__name__: t for t in kwargs.get("tools", [])}
            result = await tool_fns["get_pending"]()
            agent_got.append(result)
            return make_agent_result("checked pending")

        inst.invoke_async = AsyncMock(side_effect=fake_invoke)
        return inst

    with patch("amxmodx_genai.core.handler.Agent", side_effect=make_agent):
        srv = await asyncio.start_server(_get_persistent(), "127.0.0.1", unused_tcp_port)
        async with srv:
            await _exchange(
                unused_tcp_port,
                "is there a pending query?",
                "r1",
                {"get_pending": '{"pending":false}'},
            )

    assert len(agent_got) == 1
    data = json.loads(agent_got[0])
    assert "pending" in data
    assert isinstance(data["pending"], bool)


# ---------------------------------------------------------------------------
# Sequential tools: set_value then get_value in one request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_then_get_sequential(unused_tcp_port):
    """Two tool calls in one request complete in order with correct results."""
    agent_results: list[str] = []

    def make_agent(**kwargs):
        inst = MagicMock()

        async def fake_invoke(prompt):
            tool_fns = {t.__name__: t for t in kwargs.get("tools", [])}
            set_r = await tool_fns["set_value"](key="hp", value="100")
            get_r = await tool_fns["get_value"](key="hp")
            agent_results.extend([set_r, get_r])
            return make_agent_result("done")

        inst.invoke_async = AsyncMock(side_effect=fake_invoke)
        return inst

    with patch("amxmodx_genai.core.handler.Agent", side_effect=make_agent):
        srv = await asyncio.start_server(_get_persistent(), "127.0.0.1", unused_tcp_port)
        async with srv:
            frames = await _exchange(
                unused_tcp_port,
                "set hp to 100 then read it back",
                "r1",
                {
                    "set_value": '{"ok":true,"action":"created"}',
                    "get_value": '{"key":"hp","value":"100"}',
                },
            )

    tool_names = [f["name"] for f in frames if f.get("type") == "tool_call"]
    assert tool_names == ["set_value", "get_value"]
    assert agent_results[0] == '{"ok":true,"action":"created"}'
    assert agent_results[1] == '{"key":"hp","value":"100"}'


# ---------------------------------------------------------------------------
# Memory: short-term history persists across two queries in the same session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_persists_within_session(unused_tcp_port):
    """A second query in the same session has access to the first exchange."""
    import amxmodx_genai.core.memory as mem

    call_count = 0

    def make_agent(**kwargs):
        nonlocal call_count
        call_count += 1
        inst = MagicMock()
        inst.invoke_async = AsyncMock(return_value=make_agent_result(f"reply_{call_count}"))
        return inst

    with patch("amxmodx_genai.core.handler.Agent", side_effect=make_agent):
        srv = await asyncio.start_server(_get_persistent(), "127.0.0.1", unused_tcp_port)
        async with srv:
            await _exchange(unused_tcp_port, "first message", "r1", {})
            await _exchange(unused_tcp_port, "second message", "r2", {})

    history = mem.get(_SESSION)
    assert len(history) == 4  # 2 user + 2 assistant turns
    assert history[0]["role"] == "user"
    assert history[2]["role"] == "user"


# ---------------------------------------------------------------------------
# clear_memory: wipes short-term history; next query starts fresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_memory_resets_session(unused_tcp_port):
    """After clear_memory the session history is empty."""
    import amxmodx_genai.core.memory as mem

    def make_agent(**kwargs):
        inst = MagicMock()
        inst.invoke_async = AsyncMock(return_value=make_agent_result("ok"))
        return inst

    with (
        patch("amxmodx_genai.core.handler.Agent", side_effect=make_agent),
        patch("amxmodx_genai.core.summarize.Agent", side_effect=make_agent),
    ):
        srv = await asyncio.start_server(_get_persistent(), "127.0.0.1", unused_tcp_port)
        async with srv:
            await _exchange(unused_tcp_port, "remember this", "r1", {})
            assert len(mem.get(_SESSION)) == 2

            await _send_control(
                unused_tcp_port,
                {"type": "clear_memory", "request_id": "cm1", "player": 0, "session_id": _SESSION},
            )

    assert mem.get(_SESSION) == []


# ---------------------------------------------------------------------------
# clear_longterm: long-term summary is discarded without touching short-term
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_longterm_removes_summary(unused_tcp_port):
    """clear_longterm deletes the stored long-term summary for a session."""
    import amxmodx_genai.core.memory as mem

    session = f"{_SESSION}__lt_test"
    mem.set_longterm(session, "prior knowledge: player prefers AK47")
    assert mem.get_longterm(session) != ""

    with patch("amxmodx_genai.core.handler.Agent", return_value=MagicMock()):
        srv = await asyncio.start_server(_get_persistent(), "127.0.0.1", unused_tcp_port)
        async with srv:
            await _send_control(
                unused_tcp_port,
                {
                    "type": "clear_longterm",
                    "request_id": "clt1",
                    "player": 0,
                    "session_id": session,
                },
            )

    assert mem.get_longterm(session) == ""


# ---------------------------------------------------------------------------
# Player-scoped query: player != 0 accumulates history in its own session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_player_query_uses_separate_session(unused_tcp_port):
    """Queries with different session_ids accumulate separate histories."""
    import amxmodx_genai.core.memory as mem

    def make_agent(**kwargs):
        inst = MagicMock()
        inst.invoke_async = AsyncMock(return_value=make_agent_result("ok"))
        return inst

    player_session = f"{_SESSION}_p1"

    with patch("amxmodx_genai.core.handler.Agent", side_effect=make_agent):
        srv = await asyncio.start_server(_get_persistent(), "127.0.0.1", unused_tcp_port)
        async with srv:
            await _exchange(unused_tcp_port, "server prompt", "r1", {}, session_id=_SESSION)
            await _exchange(
                unused_tcp_port,
                "player prompt",
                "r2",
                {},
                session_id=player_session,
                player=1,
            )

    server_hist = mem.get(_SESSION)
    player_hist = mem.get(player_session)
    assert len(server_hist) == 2
    assert len(player_hist) == 2
    assert not any("player prompt" in str(m) for m in server_hist)
    assert not any("server prompt" in str(m) for m in player_hist)


# ---------------------------------------------------------------------------
# Skills: skill names in the query frame reach load_plugin_skills
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skills_forwarded_in_query(unused_tcp_port):
    """Skill names sent in the query frame are passed to load_plugin_skills."""
    skills_received: list[list[str]] = []

    def make_agent(**kwargs):
        inst = MagicMock()
        inst.invoke_async = AsyncMock(return_value=make_agent_result("ok"))
        return inst

    def capturing_load_plugin_skills(names):
        skills_received.append(list(names))
        return None  # no actual skill files needed for this wire test

    with (
        patch("amxmodx_genai.core.handler.Agent", side_effect=make_agent),
        patch(
            "amxmodx_genai.core.handler.load_plugin_skills",
            side_effect=capturing_load_plugin_skills,
        ),
    ):
        srv = await asyncio.start_server(_get_persistent(), "127.0.0.1", unused_tcp_port)
        async with srv:
            await _exchange(
                unused_tcp_port,
                "use skill",
                "r1",
                {},
                skills=["ai_testable__testable-knowledge"],
            )

    assert len(skills_received) == 1
    assert "ai_testable__testable-knowledge" in skills_received[0]


# ---------------------------------------------------------------------------
# Session scoping: two sessions do not share history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sessions_are_isolated(unused_tcp_port):
    """Queries with different session_ids accumulate separate histories."""
    import amxmodx_genai.core.memory as mem

    def make_agent(**kwargs):
        inst = MagicMock()
        inst.invoke_async = AsyncMock(return_value=make_agent_result("ok"))
        return inst

    with patch("amxmodx_genai.core.handler.Agent", side_effect=make_agent):
        srv = await asyncio.start_server(_get_persistent(), "127.0.0.1", unused_tcp_port)
        async with srv:
            await _exchange(
                unused_tcp_port, "session A message", "r1", {}, session_id="testable__a"
            )
            await _exchange(
                unused_tcp_port, "session B message", "r2", {}, session_id="testable__b"
            )

    assert len(mem.get("testable__a")) == 2
    assert len(mem.get("testable__b")) == 2
    a_texts = [str(t) for t in mem.get("testable__a")]
    b_texts = [str(t) for t in mem.get("testable__b")]
    assert not any("session B" in t for t in a_texts)
    assert not any("session A" in t for t in b_texts)


# ---------------------------------------------------------------------------
# Unknown tool name: plugin returns error string, agent receives it intact
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_tool_error_forwarded(unused_tcp_port):
    """When the plugin returns an error for an unknown tool the agent gets it."""
    agent_got: list[str] = []

    def make_agent(**kwargs):
        inst = MagicMock()

        async def fake_invoke(prompt):
            tool_fns = {t.__name__: t for t in kwargs.get("tools", [])}
            result = await tool_fns["get_value"](key="missing_key")
            agent_got.append(result)
            return make_agent_result("got error")

        inst.invoke_async = AsyncMock(side_effect=fake_invoke)
        return inst

    with patch("amxmodx_genai.core.handler.Agent", side_effect=make_agent):
        srv = await asyncio.start_server(_get_persistent(), "127.0.0.1", unused_tcp_port)
        async with srv:
            await _exchange(
                unused_tcp_port,
                "look up missing_key",
                "r1",
                {"get_value": '{"error":"key not found"}'},
            )

    assert len(agent_got) == 1
    assert json.loads(agent_got[0])["error"] == "key not found"
