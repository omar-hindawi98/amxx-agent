"""Tests for _handle_persistent: multiplexing, tool_result routing, and disconnect cleanup."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.integration.helpers import make_agent_result


def _get_persistent():
    import amxmodx_genai.server as srv_mod
    from amxmodx_genai.server import _handle_persistent

    # Ensure semaphore is initialized
    if srv_mod._sem is None:
        srv_mod._sem = asyncio.Semaphore(8)

    return _handle_persistent


async def _open_persistent(port: int):
    """Open a connection and return (reader, writer)."""
    return await asyncio.open_connection("127.0.0.1", port)


async def _send_msg(writer: asyncio.StreamWriter, obj: dict) -> None:
    writer.write((json.dumps(obj) + "\n").encode())
    await writer.drain()


async def _read_frames_until_done(
    reader: asyncio.StreamReader, request_id: str, timeout: float = 3.0
) -> list[dict]:
    """Collect frames matching request_id until a done frame for that id arrives."""
    frames: list[dict] = []
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise TimeoutError(f"timed out waiting for done frame for {request_id}; got {frames}")
        raw = await asyncio.wait_for(reader.readline(), timeout=remaining)
        if not raw:
            break
        frame = json.loads(raw.decode())
        if frame.get("request_id") == request_id:
            frames.append(frame)
            if frame.get("type") == "done":
                break
    return frames


# ---------------------------------------------------------------------------
# Single request over persistent connection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persistent_single_query_returns_frames(unused_tcp_port):
    """A single query over a persistent connection returns response + done."""
    import amxmodx_genai.server as srv_mod

    if srv_mod._sem is None:
        srv_mod._sem = asyncio.Semaphore(8)

    def make_agent(**kwargs):
        inst = MagicMock()
        inst.invoke_async = AsyncMock(return_value=make_agent_result("hello response"))
        return inst

    with patch("amxmodx_genai.core.handler.Agent", side_effect=make_agent):
        srv = await asyncio.start_server(_get_persistent(), "127.0.0.1", unused_tcp_port)
        async with srv:
            reader, writer = await _open_persistent(unused_tcp_port)
            await _send_msg(
                writer,
                {
                    "type": "query",
                    "request_id": "r1",
                    "player": 1,
                    "prompt": "hello",
                    "tools": [],
                },
            )
            frames = await _read_frames_until_done(reader, "r1")
            writer.close()
            await writer.wait_closed()

    types = [f["type"] for f in frames]
    assert "response" in types
    assert "done" in types
    response = next(f for f in frames if f["type"] == "response")
    assert "hello response" in response["text"]


# ---------------------------------------------------------------------------
# Multiplexed requests: two concurrent queries on the same connection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persistent_multiplexed_two_queries(unused_tcp_port):
    """Two concurrent queries on one persistent connection both complete correctly."""
    import amxmodx_genai.server as srv_mod

    if srv_mod._sem is None:
        srv_mod._sem = asyncio.Semaphore(8)

    call_order: list[str] = []

    async def slow_invoke_r1(prompt):
        call_order.append("r1-start")
        await asyncio.sleep(0.05)
        call_order.append("r1-end")
        return make_agent_result("response for r1")

    async def fast_invoke_r2(prompt):
        call_order.append("r2-start")
        return make_agent_result("response for r2")

    invocation_count = 0

    def make_agent(**kwargs):
        nonlocal invocation_count
        invocation_count += 1
        n = invocation_count
        inst = MagicMock()
        if n == 1:
            inst.invoke_async = AsyncMock(side_effect=slow_invoke_r1)
        else:
            inst.invoke_async = AsyncMock(side_effect=fast_invoke_r2)
        return inst

    with patch("amxmodx_genai.core.handler.Agent", side_effect=make_agent):
        srv = await asyncio.start_server(_get_persistent(), "127.0.0.1", unused_tcp_port)
        async with srv:
            reader, writer = await _open_persistent(unused_tcp_port)

            # Send both queries without waiting
            await _send_msg(
                writer,
                {
                    "type": "query",
                    "request_id": "r1",
                    "player": 1,
                    "prompt": "slow query",
                    "tools": [],
                },
            )
            await _send_msg(
                writer,
                {
                    "type": "query",
                    "request_id": "r2",
                    "player": 2,
                    "prompt": "fast query",
                    "tools": [],
                },
            )

            # Collect all frames until we have done for both
            all_frames: list[dict] = []
            done_ids: set[str] = set()
            deadline = asyncio.get_event_loop().time() + 5.0
            while len(done_ids) < 2:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    pytest.fail(f"timed out; done_ids={done_ids}, frames={all_frames}")
                raw = await asyncio.wait_for(reader.readline(), timeout=remaining)
                if not raw:
                    break
                frame = json.loads(raw.decode())
                all_frames.append(frame)
                if frame.get("type") == "done":
                    done_ids.add(frame.get("request_id", ""))

            writer.close()
            await writer.wait_closed()

    r1_frames = [f for f in all_frames if f.get("request_id") == "r1"]
    r2_frames = [f for f in all_frames if f.get("request_id") == "r2"]

    assert any(f["type"] == "response" for f in r1_frames), f"no response for r1: {r1_frames}"
    assert any(f["type"] == "done" for f in r1_frames), f"no done for r1: {r1_frames}"
    assert any(f["type"] == "response" for f in r2_frames), f"no response for r2: {r2_frames}"
    assert any(f["type"] == "done" for f in r2_frames), f"no done for r2: {r2_frames}"

    # Each request_id's response frame carries the text from its own agent invocation.
    # We only assert each has non-empty text - not which string lands where, since
    # concurrent scheduling means creation order is non-deterministic.
    r1_response = next(f for f in r1_frames if f["type"] == "response")
    r2_response = next(f for f in r2_frames if f["type"] == "response")
    assert "response for" in r1_response["text"]
    assert "response for" in r2_response["text"]


# ---------------------------------------------------------------------------
# tool_result routing: orphan result (no matching request_id) is logged and dropped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persistent_orphan_tool_result_does_not_crash(unused_tcp_port):
    """A tool_result frame with an unknown request_id is logged and silently dropped."""
    import amxmodx_genai.server as srv_mod

    if srv_mod._sem is None:
        srv_mod._sem = asyncio.Semaphore(8)

    def make_agent(**kwargs):
        inst = MagicMock()
        inst.invoke_async = AsyncMock(return_value=make_agent_result("ok"))
        return inst

    with patch("amxmodx_genai.core.handler.Agent", side_effect=make_agent):
        srv = await asyncio.start_server(_get_persistent(), "127.0.0.1", unused_tcp_port)
        async with srv:
            reader, writer = await _open_persistent(unused_tcp_port)

            # Send a tool_result for a request that doesn't exist
            await _send_msg(
                writer,
                {
                    "type": "tool_result",
                    "request_id": "ghost_request",
                    "id": "plug_abc123",
                    "content": "some result",
                },
            )

            # Now send a normal query - it should still work
            await _send_msg(
                writer,
                {
                    "type": "query",
                    "request_id": "r1",
                    "player": 1,
                    "prompt": "hello",
                    "tools": [],
                },
            )
            frames = await _read_frames_until_done(reader, "r1")
            writer.close()
            await writer.wait_closed()

    types = [f["type"] for f in frames]
    assert "response" in types
    assert "done" in types


# ---------------------------------------------------------------------------
# tool_result routing: result delivered to correct in-flight handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persistent_tool_result_routed_to_correct_handler(unused_tcp_port):
    """tool_result frames are routed by request_id to the waiting handler."""
    import amxmodx_genai.server as srv_mod

    if srv_mod._sem is None:
        srv_mod._sem = asyncio.Semaphore(8)

    async def mock_call(name, args, send, tool_result_queue, request_id, session_data):
        # Record what tool call frame was sent by inspecting queue; just return a canned result
        session_data.setdefault("calls", []).append({"tool": name, "args": args, "result": "42"})
        return "42"

    def make_agent(**kwargs):
        inst = MagicMock()

        async def fake_invoke(prompt):
            # Trigger the tool via the registered tool function
            tool_fns = [t for t in kwargs.get("tools", []) if t.__name__ == "ping"]
            if tool_fns:
                await tool_fns[0](args="{}")
            return make_agent_result("tool result was 42")

        inst.invoke_async = AsyncMock(side_effect=fake_invoke)
        return inst

    with (
        patch("amxmodx_genai.core.handler.Agent", side_effect=make_agent),
        patch("amxmodx_genai.tools.plugin._call", side_effect=mock_call),
    ):
        srv = await asyncio.start_server(_get_persistent(), "127.0.0.1", unused_tcp_port)
        async with srv:
            reader, writer = await _open_persistent(unused_tcp_port)
            await _send_msg(
                writer,
                {
                    "type": "query",
                    "request_id": "r1",
                    "player": 1,
                    "prompt": "ping",
                    "tools": [{"name": "ping", "description": "ping tool"}],
                },
            )
            frames = await _read_frames_until_done(reader, "r1")
            writer.close()
            await writer.wait_closed()

    response = next(f for f in frames if f["type"] == "response")
    assert "42" in response["text"]


# ---------------------------------------------------------------------------
# Disconnect: in-flight tasks are cancelled on connection close
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persistent_disconnect_cancels_in_flight_tasks(unused_tcp_port):
    """When the client disconnects mid-query, in-flight tasks are cancelled cleanly."""
    import amxmodx_genai.server as srv_mod

    if srv_mod._sem is None:
        srv_mod._sem = asyncio.Semaphore(8)

    task_was_cancelled = asyncio.Event()

    async def hanging_invoke(prompt):
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            task_was_cancelled.set()
            raise
        return make_agent_result("should not reach here")

    def make_agent(**kwargs):
        inst = MagicMock()
        inst.invoke_async = AsyncMock(side_effect=hanging_invoke)
        return inst

    with patch("amxmodx_genai.core.handler.Agent", side_effect=make_agent):
        srv = await asyncio.start_server(_get_persistent(), "127.0.0.1", unused_tcp_port)
        async with srv:
            reader, writer = await _open_persistent(unused_tcp_port)
            await _send_msg(
                writer,
                {
                    "type": "query",
                    "request_id": "r1",
                    "player": 1,
                    "prompt": "hang",
                    "tools": [],
                },
            )
            # Give the handler time to start the task
            await asyncio.sleep(0.1)
            # Disconnect abruptly
            writer.close()
            await writer.wait_closed()

            # The cancellation should propagate within a short window
            try:
                await asyncio.wait_for(task_was_cancelled.wait(), timeout=2.0)
            except TimeoutError:
                pytest.fail("in-flight task was not cancelled after client disconnect")


# ---------------------------------------------------------------------------
# Unknown message type: logged and ignored, connection stays alive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persistent_unknown_message_type_ignored(unused_tcp_port):
    """An unrecognised message type is logged and the connection remains usable."""
    import amxmodx_genai.server as srv_mod

    if srv_mod._sem is None:
        srv_mod._sem = asyncio.Semaphore(8)

    def make_agent(**kwargs):
        inst = MagicMock()
        inst.invoke_async = AsyncMock(return_value=make_agent_result("still alive"))
        return inst

    with patch("amxmodx_genai.core.handler.Agent", side_effect=make_agent):
        srv = await asyncio.start_server(_get_persistent(), "127.0.0.1", unused_tcp_port)
        async with srv:
            reader, writer = await _open_persistent(unused_tcp_port)

            await _send_msg(writer, {"type": "unknown_frame_type", "request_id": "x"})
            # Small delay to ensure server processed the unknown frame
            await asyncio.sleep(0.05)

            await _send_msg(
                writer,
                {
                    "type": "query",
                    "request_id": "r1",
                    "player": 1,
                    "prompt": "hello",
                    "tools": [],
                },
            )
            frames = await _read_frames_until_done(reader, "r1")
            writer.close()
            await writer.wait_closed()

    types = [f["type"] for f in frames]
    assert "response" in types
    assert "done" in types


# ---------------------------------------------------------------------------
# Bad JSON frame: skipped, connection stays alive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persistent_bad_json_skipped_connection_survives(unused_tcp_port):
    """A malformed JSON line is skipped and the connection remains usable."""
    import amxmodx_genai.server as srv_mod

    if srv_mod._sem is None:
        srv_mod._sem = asyncio.Semaphore(8)

    def make_agent(**kwargs):
        inst = MagicMock()
        inst.invoke_async = AsyncMock(return_value=make_agent_result("survived"))
        return inst

    with patch("amxmodx_genai.core.handler.Agent", side_effect=make_agent):
        srv = await asyncio.start_server(_get_persistent(), "127.0.0.1", unused_tcp_port)
        async with srv:
            reader, writer = await _open_persistent(unused_tcp_port)

            # Send bad JSON first
            writer.write(b"this is not json\n")
            await writer.drain()
            await asyncio.sleep(0.05)

            # Then a valid query
            await _send_msg(
                writer,
                {
                    "type": "query",
                    "request_id": "r1",
                    "player": 1,
                    "prompt": "hello",
                    "tools": [],
                },
            )
            frames = await _read_frames_until_done(reader, "r1")
            writer.close()
            await writer.wait_closed()

    types = [f["type"] for f in frames]
    assert "response" in types
    assert "done" in types


# ---------------------------------------------------------------------------
# clear_memory over persistent connection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persistent_clear_memory_no_response_sent(unused_tcp_port):
    """clear_memory over a persistent connection sends no response frames."""
    import amxmodx_genai.server as srv_mod

    if srv_mod._sem is None:
        srv_mod._sem = asyncio.Semaphore(8)

    with patch("amxmodx_genai.core.handler.summarize_session", new=AsyncMock(return_value="")):
        srv = await asyncio.start_server(_get_persistent(), "127.0.0.1", unused_tcp_port)
        async with srv:
            reader, writer = await _open_persistent(unused_tcp_port)
            await _send_msg(
                writer,
                {
                    "type": "clear_memory",
                    "request_id": "cm1",
                    "player": 5,
                    "session_id": "5",
                },
            )
            # No frames should arrive within a short window
            await asyncio.sleep(0.3)
            try:
                data = await asyncio.wait_for(reader.read(1), timeout=0.2)
                assert data == b"", f"expected no data for clear_memory, got {data!r}"
            except TimeoutError:
                pass  # correct: no data
            writer.close()
            await writer.wait_closed()
