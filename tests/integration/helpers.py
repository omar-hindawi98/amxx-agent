"""Shared helpers for integration tests (non-fixture utilities)."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock


def get_handle():
    from amxmodx_genai.server import handle_once

    return handle_once


def make_agent_result(text: str) -> MagicMock:
    block = MagicMock()
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    result = MagicMock()
    result.message = msg
    return result


def make_agent_factory(text: str = "ok", *, invoke_side_effect=None):
    """Return a capture_agent factory + captured_kwargs dict."""
    captured_kwargs: dict = {}

    def capture_agent(**kwargs):
        captured_kwargs.update(kwargs)
        inst = MagicMock()
        if invoke_side_effect is not None:
            inst.invoke_async = AsyncMock(side_effect=invoke_side_effect)
        else:
            inst.invoke_async = AsyncMock(return_value=make_agent_result(text))
        return inst

    return capture_agent, captured_kwargs


async def tcp_exchange(host: str, port: int, msg: dict) -> list[dict]:
    """Send one JSON message; read all response frames until type=done."""
    reader, writer = await asyncio.open_connection(host, port)
    writer.write((json.dumps(msg) + "\n").encode())
    await writer.drain()

    frames: list[dict] = []
    while True:
        raw = await asyncio.wait_for(reader.readline(), timeout=5.0)
        if not raw:
            break
        frame = json.loads(raw.decode())
        frames.append(frame)
        if frame.get("type") == "done":
            break

    writer.close()
    await writer.wait_closed()
    return frames
