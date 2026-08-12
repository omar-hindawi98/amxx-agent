"""Unit tests for the plugin tool factory."""

import asyncio
import json

import pytest

from amxmodx_genai.tools.plugin import _build_input_schema, make_plugin_tool

# ---------------------------------------------------------------------------
# _build_input_schema
# ---------------------------------------------------------------------------


def test_build_schema_empty_params():
    schema = _build_input_schema([])
    assert schema == {"type": "object", "properties": {}, "additionalProperties": False}
    assert "required" not in schema


def test_build_schema_required_and_optional():
    params = [
        {"name": "player_id", "type": "integer", "required": True, "description": "Player index"},
        {"name": "verbose", "type": "boolean", "required": False, "description": "Extra output"},
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


def _make_writer_reader_pair():
    """Create an asyncio.StreamReader and a mock writer that echoes tool_results."""
    from unittest.mock import AsyncMock, MagicMock

    writer = MagicMock(spec=asyncio.StreamWriter)
    writer.drain = AsyncMock()
    written: list[bytes] = []

    reader = asyncio.StreamReader()

    def capture_write(data: bytes) -> None:
        written.append(data)
        # Parse the tool_call and feed back a matching tool_result.
        try:
            msg = json.loads(data.decode().strip())
            if msg.get("type") == "tool_call":
                resp = json.dumps(
                    {"type": "tool_result", "id": msg["id"], "content": "test_result"}
                )
                reader.feed_data((resp + "\n").encode())
        except Exception:
            pass

    writer.write = capture_write
    return reader, writer, written


@pytest.mark.asyncio
async def test_no_params_tool_sends_args_string():
    """Without params, the tool accepts a free-form args string."""
    reader, writer, written = _make_writer_reader_pair()
    session_data: dict = {}

    t = make_plugin_tool("myplugin__get_map", "Returns map name", reader, writer, session_data)
    fn = t.func if hasattr(t, "func") else t
    result = await fn(args='{"format":"short"}')
    assert result == "test_result"

    sent = json.loads(b"".join(written).decode().strip())
    assert sent["type"] == "tool_call"
    assert sent["name"] == "myplugin__get_map"
    assert sent["args"] == '{"format":"short"}'


@pytest.mark.asyncio
async def test_with_params_tool_serializes_kwargs():
    """With params, the tool receives typed kwargs and serializes them to args JSON."""
    params = [
        {"name": "player_id", "type": "integer", "required": True, "description": "Player index"},
    ]
    reader, writer, written = _make_writer_reader_pair()
    session_data: dict = {}

    t = make_plugin_tool(
        "myplugin__get_player", "Get player", reader, writer, session_data, params=params
    )
    fn = t.func if hasattr(t, "func") else t
    result = await fn(player_id=3)
    assert result == "test_result"

    sent = json.loads(b"".join(written).decode().strip())
    assert sent["name"] == "myplugin__get_player"
    assert json.loads(sent["args"]) == {"player_id": 3}


@pytest.mark.asyncio
async def test_session_data_records_call():
    reader, writer, _ = _make_writer_reader_pair()
    session_data: dict = {}

    t = make_plugin_tool("myplugin__x", "X tool", reader, writer, session_data)
    fn = t.func if hasattr(t, "func") else t
    await fn(args="{}")

    assert len(session_data["calls"]) == 1
    assert session_data["calls"][0]["tool"] == "myplugin__x"
    assert session_data["calls"][0]["result"] == "test_result"
