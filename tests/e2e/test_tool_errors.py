"""Tests for plugin tool error handling: timeout, closed connection, bad frames."""

import asyncio

import pytest


@pytest.mark.asyncio
async def test_tool_call_timeout_returns_sentinel():
    """When a plugin tool call times out, _call returns the timeout sentinel."""
    from amxmodx_genai.tools import plugin as plugin_mod

    async def fake_send(obj: dict) -> None:
        pass

    tool_result_queue: asyncio.Queue = asyncio.Queue()
    session_data: dict = {}

    loop = asyncio.get_running_loop()
    original_time = loop.time
    call_count = 0

    def patched_time():
        nonlocal call_count
        call_count += 1
        return 0 if call_count == 1 else 100

    loop.time = patched_time
    try:
        result = await plugin_mod._call(
            "get_player_info", "{}", fake_send, tool_result_queue, "req1", session_data
        )
    finally:
        loop.time = original_time

    assert result == "(tool call timed out)"
    assert session_data["calls"][0]["error"] == "tool call timed out"


@pytest.mark.asyncio
async def test_tool_call_result_returned_from_queue():
    """A matching tool_result frame in the queue is returned as the result."""
    from amxmodx_genai.tools import plugin as plugin_mod

    call_id_seen: list[str] = []

    async def fake_send(obj: dict) -> None:
        if obj.get("type") == "tool_call":
            call_id_seen.append(obj["id"])

    tool_result_queue: asyncio.Queue = asyncio.Queue()
    session_data: dict = {}

    async def inject_result():
        for _ in range(50):
            if call_id_seen:
                break
            await asyncio.sleep(0.01)
        await tool_result_queue.put(
            {"type": "tool_result", "id": call_id_seen[0], "content": "correct_result"}
        )

    inject_task = asyncio.create_task(inject_result())
    result = await plugin_mod._call(
        "kick_player", "{}", fake_send, tool_result_queue, "req2", session_data
    )
    await inject_task

    assert result == "correct_result"
    assert session_data["calls"][0]["result"] == "correct_result"


@pytest.mark.asyncio
async def test_tool_call_discards_frames_with_wrong_id():
    """Frames with a mismatched id are re-queued; the matching frame is returned."""
    from amxmodx_genai.tools import plugin as plugin_mod

    call_id_seen: list[str] = []

    async def fake_send(obj: dict) -> None:
        if obj.get("type") == "tool_call":
            call_id_seen.append(obj["id"])

    tool_result_queue: asyncio.Queue = asyncio.Queue()
    session_data: dict = {}

    await tool_result_queue.put({"type": "tool_result", "id": "wrong_id", "content": "ignored"})

    async def inject_correct_frame():
        for _ in range(50):
            if call_id_seen:
                break
            await asyncio.sleep(0.01)
        await tool_result_queue.put(
            {"type": "tool_result", "id": call_id_seen[0], "content": "correct_result"}
        )

    inject_task = asyncio.create_task(inject_correct_frame())
    result = await plugin_mod._call("say", "{}", fake_send, tool_result_queue, "req3", session_data)
    await inject_task

    assert result == "correct_result"
    assert session_data["calls"][0]["result"] == "correct_result"


@pytest.mark.asyncio
async def test_tool_call_send_called_with_correct_frame():
    """_call sends a tool_call frame with the correct name, args, and request_id."""
    from amxmodx_genai.tools import plugin as plugin_mod

    sent: list[dict] = []
    call_id_seen: list[str] = []

    async def fake_send(obj: dict) -> None:
        sent.append(obj)
        if obj.get("type") == "tool_call":
            call_id_seen.append(obj["id"])

    tool_result_queue: asyncio.Queue = asyncio.Queue()
    session_data: dict = {}

    async def inject_result():
        for _ in range(50):
            if call_id_seen:
                break
            await asyncio.sleep(0.01)
        await tool_result_queue.put({"type": "tool_result", "id": call_id_seen[0], "content": "ok"})

    inject_task = asyncio.create_task(inject_result())
    await plugin_mod._call(
        "say", '{"msg":"hi"}', fake_send, tool_result_queue, "req4", session_data
    )
    await inject_task

    assert len(sent) == 1
    assert sent[0]["type"] == "tool_call"
    assert sent[0]["name"] == "say"
    assert sent[0]["args"] == '{"msg":"hi"}'
    assert sent[0]["request_id"] == "req4"
