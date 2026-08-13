"""Tests for plugin tool error handling: timeout, closed connection, bad frames."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_tool_call_timeout_returns_sentinel():
    """When a plugin tool call times out, _call returns the timeout sentinel."""
    from amxmodx_genai.tools import plugin as plugin_mod

    reader = MagicMock(spec=asyncio.StreamReader)
    writer = MagicMock(spec=asyncio.StreamWriter)
    writer.drain = AsyncMock()
    session_data: dict = {}

    async def timeout_readline():
        raise TimeoutError()

    reader.readline = timeout_readline

    loop = asyncio.get_running_loop()
    original_time = loop.time
    call_count = 0

    def patched_time():
        nonlocal call_count
        call_count += 1
        return 0 if call_count == 1 else 100

    loop.time = patched_time
    try:
        result = await plugin_mod._call("get_player_info", "{}", reader, writer, session_data)
    finally:
        loop.time = original_time

    assert result == "(tool call timed out)"
    assert session_data["calls"][0]["error"] == "tool call timed out"


@pytest.mark.asyncio
async def test_tool_call_plugin_closed_connection_returns_sentinel():
    """When plugin closes connection mid-tool-call, _call returns the closed sentinel."""
    from amxmodx_genai.tools import plugin as plugin_mod

    reader = MagicMock(spec=asyncio.StreamReader)
    writer = MagicMock(spec=asyncio.StreamWriter)
    writer.drain = AsyncMock()
    session_data: dict = {}

    async def eof_readline():
        return b""

    reader.readline = eof_readline

    result = await plugin_mod._call("kick_player", "{}", reader, writer, session_data)

    assert result == "(plugin closed connection)"
    assert session_data["calls"][0]["error"] == "plugin closed connection"


@pytest.mark.asyncio
async def test_tool_call_discards_frames_with_wrong_id():
    """Frames with a mismatched id are discarded; the matching frame is returned."""
    from amxmodx_genai.tools import plugin as plugin_mod

    reader = MagicMock(spec=asyncio.StreamReader)
    writer = MagicMock(spec=asyncio.StreamWriter)
    writer.drain = AsyncMock()
    session_data: dict = {}

    call_id_seen: list[str] = []

    def capture_write(data):
        try:
            frame = json.loads(data.decode().strip())
            if frame.get("type") == "tool_call":
                call_id_seen.append(frame["id"])
        except Exception:
            pass

    writer.write = capture_write

    frames_queue: asyncio.Queue = asyncio.Queue()

    async def queued_readline():
        return await frames_queue.get()

    reader.readline = queued_readline
    await frames_queue.put(
        json.dumps({"type": "tool_result", "id": "wrong_id", "content": "ignored"}).encode() + b"\n"
    )

    async def inject_correct_frame():
        for _ in range(50):
            if call_id_seen:
                break
            await asyncio.sleep(0.01)
        await frames_queue.put(
            json.dumps(
                {"type": "tool_result", "id": call_id_seen[0], "content": "correct_result"}
            ).encode()
            + b"\n"
        )

    inject_task = asyncio.create_task(inject_correct_frame())
    result = await plugin_mod._call("say", "{}", reader, writer, session_data)
    await inject_task

    assert result == "correct_result"
    assert session_data["calls"][0]["result"] == "correct_result"


@pytest.mark.asyncio
async def test_tool_call_skips_malformed_json_frames():
    """Malformed JSON frames are skipped; the next valid matching frame is returned."""
    from amxmodx_genai.tools import plugin as plugin_mod

    reader = MagicMock(spec=asyncio.StreamReader)
    writer = MagicMock(spec=asyncio.StreamWriter)
    writer.drain = AsyncMock()
    session_data: dict = {}

    call_id_seen: list[str] = []

    def capture_write(data):
        try:
            frame = json.loads(data.decode().strip())
            if frame.get("type") == "tool_call":
                call_id_seen.append(frame["id"])
        except Exception:
            pass

    writer.write = capture_write

    frames_queue: asyncio.Queue = asyncio.Queue()

    async def queued_readline():
        return await frames_queue.get()

    reader.readline = queued_readline
    await frames_queue.put(b"not valid json\n")

    async def inject_correct_frame():
        for _ in range(50):
            if call_id_seen:
                break
            await asyncio.sleep(0.01)
        await frames_queue.put(
            json.dumps({"type": "tool_result", "id": call_id_seen[0], "content": "valid"}).encode()
            + b"\n"
        )

    inject_task = asyncio.create_task(inject_correct_frame())
    result = await plugin_mod._call("say", "{}", reader, writer, session_data)
    await inject_task

    assert result == "valid"
