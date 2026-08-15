"""Unit tests for the plugin tool factory."""

import asyncio
import json

import pytest

from amxx_agent.tools.plugin import _build_input_schema, make_plugin_tool

# ---------------------------------------------------------------------------
# _build_input_schema
# ---------------------------------------------------------------------------


def test_build_schema_empty_params():
    schema = _build_input_schema([])
    assert schema == {"type": "object", "properties": {}, "additionalProperties": False}
    assert "required" not in schema


def test_build_schema_required_and_optional():
    params = [
        {
            "name": "player_id",
            "type": "integer",
            "required": True,
            "description": "Player index",
        },
        {
            "name": "verbose",
            "type": "boolean",
            "required": False,
            "description": "Extra output",
        },
    ]
    schema = _build_input_schema(params)
    assert schema["properties"]["player_id"] == {
        "type": "integer",
        "description": "Player index",
    }
    assert schema["properties"]["verbose"] == {
        "type": "boolean",
        "description": "Extra output",
    }
    assert schema["required"] == ["player_id"]
    assert "verbose" not in schema.get("required", [])


def test_build_schema_all_types():
    params = [
        {"name": "s", "type": "string", "required": False, "description": ""},
        {"name": "i", "type": "integer", "required": False, "description": ""},
        {"name": "b", "type": "boolean", "required": False, "description": ""},
        {"name": "n", "type": "number", "required": False, "description": ""},
    ]
    schema = _build_input_schema(params)
    assert schema["properties"]["s"]["type"] == "string"
    assert schema["properties"]["i"]["type"] == "integer"
    assert schema["properties"]["b"]["type"] == "boolean"
    assert schema["properties"]["n"]["type"] == "number"


def test_build_schema_unknown_type_defaults_to_string():
    params = [{"name": "x", "type": "blob", "required": False, "description": ""}]
    schema = _build_input_schema(params)
    assert schema["properties"]["x"]["type"] == "string"


def test_build_schema_additional_properties_false():
    schema = _build_input_schema(
        [{"name": "x", "type": "string", "required": False, "description": ""}]
    )
    assert schema["additionalProperties"] is False


def test_build_schema_skips_param_without_name():
    params = [
        {"type": "string", "required": False, "description": "no name"},
        {"name": "valid", "type": "string", "required": False, "description": ""},
    ]
    schema = _build_input_schema(params)
    assert list(schema["properties"].keys()) == ["valid"]


# ---------------------------------------------------------------------------
# make_plugin_tool - round-trip behavior
# ---------------------------------------------------------------------------


def _make_send_queue_pair():
    """Create a send coroutine and a tool_result_queue that auto-replies to tool_calls."""
    sent: list[dict] = []
    queue: asyncio.Queue = asyncio.Queue()

    async def send(obj: dict) -> None:
        sent.append(obj)
        if obj.get("type") == "tool_call":
            await queue.put({"type": "tool_result", "id": obj["id"], "content": "test_result"})

    return send, queue, sent


@pytest.mark.asyncio
async def test_no_params_tool_sends_args_string():
    """Without params, the tool accepts a free-form args string."""
    send, queue, sent = _make_send_queue_pair()
    session_data: dict = {}

    t = make_plugin_tool("myplugin__get_map", "Returns map name", send, queue, "req1", session_data)
    fn = t.func if hasattr(t, "func") else t
    result = await fn(args='{"format":"short"}')
    assert result == "test_result"

    call = next(m for m in sent if m.get("type") == "tool_call")
    assert call["name"] == "myplugin__get_map"
    assert call["args"] == '{"format":"short"}'
    assert call["request_id"] == "req1"


@pytest.mark.asyncio
async def test_with_params_tool_serializes_kwargs():
    """With params, the tool receives typed kwargs and serializes them to args JSON."""
    params = [
        {
            "name": "player_id",
            "type": "integer",
            "required": True,
            "description": "Player index",
        },
    ]
    send, queue, sent = _make_send_queue_pair()
    session_data: dict = {}

    t = make_plugin_tool(
        "myplugin__get_player",
        "Get player",
        send,
        queue,
        "req2",
        session_data,
        params=params,
    )
    fn = t.func if hasattr(t, "func") else t
    result = await fn(player_id=3)
    assert result == "test_result"

    call = next(m for m in sent if m.get("type") == "tool_call")
    assert call["name"] == "myplugin__get_player"
    assert json.loads(call["args"]) == {"player_id": 3}


@pytest.mark.asyncio
async def test_session_data_records_call():
    send, queue, _ = _make_send_queue_pair()
    session_data: dict = {}

    t = make_plugin_tool("myplugin__x", "X tool", send, queue, "req3", session_data)
    fn = t.func if hasattr(t, "func") else t
    await fn(args="{}")

    assert len(session_data["calls"]) == 1
    assert session_data["calls"][0]["tool"] == "myplugin__x"
    assert session_data["calls"][0]["result"] == "test_result"
