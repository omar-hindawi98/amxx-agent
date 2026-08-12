"""
Live e2e tests - require a real sidecar running.

Skipped automatically when GENAI_SIDECAR_HOST is not set or the sidecar is
unreachable. Run explicitly with:

    GENAI_SIDECAR_HOST=127.0.0.1 pytest tests/e2e/test_live.py -m live

Or via docker compose (uses real sidecar with Ollama):

    docker compose --profile live up --abort-on-container-exit live_test

Tests assert protocol correctness and non-empty responses only.
They do NOT assert exact LLM output - that would be brittle.
"""

import asyncio
import json
import os

import pytest

SIDECAR_HOST = os.environ.get("GENAI_SIDECAR_HOST", "")
SIDECAR_PORT = int(os.environ.get("GENAI_SIDECAR_PORT", "27016"))

pytestmark = pytest.mark.live


async def exchange(msg: dict, *, timeout: float = 60.0) -> list[dict]:
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
    return [f["type"] for f in frames]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_basic_query_completes():
    frames = await exchange({"type": "query", "player": 1, "prompt": "say hello", "tools": []})
    types = frame_types(frames)
    assert "response" in types, f"no response frame: {types}"
    assert "done" in types, f"no done frame: {types}"


async def test_response_text_non_empty():
    frames = await exchange({"type": "query", "player": 1, "prompt": "say hello", "tools": []})
    response = next(f for f in frames if f["type"] == "response")
    assert response["text"].strip(), "response text was empty"


async def test_session_memory_persists():
    """Second query in same session should acknowledge the first."""
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
    await asyncio.wait_for(reader.read(1), timeout=5.0)
    writer.close()
    await writer.wait_closed()


async def test_clear_memory_accepted():
    reader, writer = await asyncio.open_connection(SIDECAR_HOST, SIDECAR_PORT)
    writer.write((json.dumps({"type": "clear_memory", "player": 99}) + "\n").encode())
    await writer.drain()
    data = await asyncio.wait_for(reader.read(1), timeout=5.0)
    assert data == b""
    writer.close()
    await writer.wait_closed()


async def test_plugin_context_injected():
    """Plugin context should influence the response."""
    frames = await exchange(
        {
            "type": "query",
            "player": 1,
            "plugin": "test_plugin",
            "system": "Always end every response with the word PINEAPPLE.",
            "prompt": "say something short",
            "tools": [],
        }
    )
    response = next(f for f in frames if f["type"] == "response")
    assert "PINEAPPLE" in response["text"], (
        f"expected PINEAPPLE in response, got: {response['text']}"
    )
