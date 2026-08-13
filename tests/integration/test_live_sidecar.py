"""
Integration tests against a real running sidecar.

Run with:

    GENAI_SIDECAR_HOST=127.0.0.1 pytest tests/integration/

Tests assert protocol correctness and non-empty responses only.
They do NOT assert exact LLM output - that would be brittle.
"""

import asyncio
import json
import os

import pytest

SIDECAR_HOST = os.environ.get("GENAI_SIDECAR_HOST", "")
SIDECAR_PORT = int(os.environ.get("GENAI_SIDECAR_PORT", "27016"))

pytestmark = pytest.mark.skipif(
    not SIDECAR_HOST,
    reason="GENAI_SIDECAR_HOST not set - skipping live sidecar tests",
)


async def exchange(msg: dict, *, timeout: float = 60.0) -> list[dict]:
    """Send a single newline-delimited JSON message and collect all response frames until done."""
    reader, writer = await asyncio.open_connection(SIDECAR_HOST, SIDECAR_PORT)
    writer.write((json.dumps(msg) + "\n").encode())
    await writer.drain()

    frames: list[dict] = []
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            pytest.fail(f"timed out waiting for done frame; got so far: {frames}")
        raw = await asyncio.wait_for(reader.readline(), timeout=remaining)
        if not raw:
            break
        frames.append(json.loads(raw.decode()))
        if frames[-1].get("type") == "done":
            break

    writer.close()
    await writer.wait_closed()
    return frames


def frame_types(frames: list[dict]) -> list[str]:
    """Return the list of frame type strings from a response sequence."""
    return [f["type"] for f in frames]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_protocol_response_and_done_frames_returned():
    """A query must produce exactly one response frame and one done frame."""
    frames = await exchange({"type": "query", "player": 1, "prompt": "say hello", "tools": []})
    types = frame_types(frames)
    assert "response" in types, f"no response frame: {types}"
    assert "done" in types, f"no done frame: {types}"


async def test_protocol_response_text_non_empty():
    """The response frame must carry non-empty text."""
    frames = await exchange({"type": "query", "player": 1, "prompt": "say hello", "tools": []})
    response = next(f for f in frames if f["type"] == "response")
    assert response["text"].strip(), "response text was empty"


async def test_memory_persists_within_session():
    """A follow-up query in the same session should recall context from the first query."""
    session = "live_test_session"
    await exchange(
        {
            "type": "query",
            "player": 1,
            "session_id": session,
            "prompt": "my favourite gun is the AK47",
            "tools": [],
        }
    )
    frames = await exchange(
        {
            "type": "query",
            "player": 1,
            "session_id": session,
            "prompt": "what gun did I mention?",
            "tools": [],
        }
    )
    response = next(f for f in frames if f["type"] == "response")
    assert "AK" in response["text"] or "ak" in response["text"].lower(), (
        f"expected AK47 in follow-up response, got: {response['text']}"
    )
    # cleanup
    reader, writer = await asyncio.open_connection(SIDECAR_HOST, SIDECAR_PORT)
    writer.write(
        (json.dumps({"type": "clear_memory", "player": 1, "session_id": session}) + "\n").encode()
    )
    await writer.drain()
    await asyncio.sleep(1.0)
    writer.close()
    await writer.wait_closed()


async def test_memory_clear_sends_no_response():
    """A clear_memory request must be processed silently - no response bytes sent."""
    reader, writer = await asyncio.open_connection(SIDECAR_HOST, SIDECAR_PORT)
    writer.write((json.dumps({"type": "clear_memory", "player": 99}) + "\n").encode())
    await writer.drain()
    try:
        data = await asyncio.wait_for(reader.read(1), timeout=1.0)
        assert data == b"", f"expected no data, got {data!r}"
    except TimeoutError:
        pass  # timeout means no data was sent, which is correct
    writer.close()
    await writer.wait_closed()


async def test_plugin_system_prompt_accepted():
    """A query with plugin name and system prompt must return a valid response frame."""
    frames = await exchange(
        {
            "type": "query",
            "player": 1,
            "plugin": "test_plugin",
            "system": "You are a helpful CS assistant.",
            "prompt": "say something short",
            "tools": [],
        }
    )
    types = frame_types(frames)
    assert "response" in types, f"no response frame: {types}"
    assert "done" in types, f"no done frame: {types}"
    response = next(f for f in frames if f["type"] == "response")
    assert response["text"].strip(), "response text was empty"
