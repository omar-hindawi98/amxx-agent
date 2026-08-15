"""Unit tests for wire protocol helpers."""

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from amxx_agent.core.protocol import read_json, send_json

# ---------------------------------------------------------------------------
# send_json
# ---------------------------------------------------------------------------


def test_send_json_writes_newline_terminated_json():
    written = []
    writer = MagicMock()
    writer.write = lambda data: written.append(data)

    send_json(writer, {"type": "ok", "value": 42})

    assert len(written) == 1
    raw = written[0]
    assert raw.endswith(b"\n")
    decoded = json.loads(raw.decode("utf-8"))
    assert decoded == {"type": "ok", "value": 42}


def test_send_json_encodes_utf8():
    written = []
    writer = MagicMock()
    writer.write = lambda data: written.append(data)

    send_json(writer, {"msg": "hello"})
    assert isinstance(written[0], bytes)


# ---------------------------------------------------------------------------
# read_json
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_json_parses_line():
    reader = asyncio.StreamReader()
    reader.feed_data(b'{"type": "query", "text": "hi"}\n')

    result = await read_json(reader)
    assert result == {"type": "query", "text": "hi"}


@pytest.mark.asyncio
async def test_read_json_returns_none_on_eof():
    reader = asyncio.StreamReader()
    reader.feed_eof()

    result = await read_json(reader)
    assert result is None


@pytest.mark.asyncio
async def test_read_json_times_out():
    reader = asyncio.StreamReader()
    # Nothing fed - readline will never return

    with pytest.raises(asyncio.TimeoutError):
        await read_json(reader, timeout=0.05)
