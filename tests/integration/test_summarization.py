"""Tests for the clear_memory -> summarize_session -> set_longterm pipeline."""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from tests.integration.helpers import get_handle


def _mem():
    import amxx_agent.core.memory as m

    return m


async def _send_clear(port: int, session_id: str, player: int = 1) -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(
        (
            json.dumps({"type": "clear_memory", "player": player, "session_id": session_id}) + "\n"
        ).encode()
    )
    await writer.drain()
    await asyncio.wait_for(reader.readline(), timeout=70.0)
    writer.close()
    await writer.wait_closed()


# ---------------------------------------------------------------------------
# summarize_session invocation conditions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summarize_called_with_session_history(unused_tcp_port):
    """clear_memory calls summarize_session with the session's current history."""
    mem = _mem()
    mem.update("s1", "what to buy?", "Buy AK47.")
    expected_history = mem.get("s1")

    with patch(
        "amxx_agent.core.handler.summarize_session",
        new=AsyncMock(return_value="- Prefers AK47"),
    ) as mock_summarize:
        srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
        async with srv:
            await _send_clear(unused_tcp_port, "s1")

    mock_summarize.assert_called_once()
    actual_history = mock_summarize.call_args[0][0]
    assert actual_history == expected_history


@pytest.mark.asyncio
async def test_empty_history_skips_summarize(unused_tcp_port):
    """clear_memory on a session with no history does not call summarize_session."""
    mem = _mem()
    assert mem.get("no_history") == []

    with patch(
        "amxx_agent.core.handler.summarize_session",
        new=AsyncMock(return_value=""),
    ) as mock_summarize:
        srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
        async with srv:
            await _send_clear(unused_tcp_port, "no_history")

    mock_summarize.assert_not_called()


@pytest.mark.asyncio
async def test_prior_longterm_passed_to_summarize(unused_tcp_port):
    """Existing long-term memory is passed as the prior_summary argument."""
    mem = _mem()
    mem.update("s2", "eco round?", "Save this round.")
    mem.set_longterm("s2", "- Player saves when low on cash")

    with patch(
        "amxx_agent.core.handler.summarize_session",
        new=AsyncMock(return_value="- updated"),
    ) as mock_summarize:
        srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
        async with srv:
            await _send_clear(unused_tcp_port, "s2")

    mock_summarize.assert_called_once()
    prior_arg = mock_summarize.call_args[0][1]
    assert prior_arg == "- Player saves when low on cash"


# ---------------------------------------------------------------------------
# long-term storage outcomes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summary_stored_as_longterm_after_clear(unused_tcp_port):
    """summarize_session return value is stored as long-term memory."""
    mem = _mem()
    mem.update("s3", "rush B?", "Yes rush B.")

    with patch(
        "amxx_agent.core.handler.summarize_session",
        new=AsyncMock(return_value="- Aggressive playstyle"),
    ):
        srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
        async with srv:
            await _send_clear(unused_tcp_port, "s3")

    assert mem.get_longterm("s3") == "- Aggressive playstyle"


@pytest.mark.asyncio
async def test_empty_summary_not_stored(unused_tcp_port):
    """When summarize_session returns empty string, long-term memory is not written."""
    mem = _mem()
    mem.update("s4", "hello", "world")

    with patch(
        "amxx_agent.core.handler.summarize_session",
        new=AsyncMock(return_value=""),
    ):
        srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
        async with srv:
            await _send_clear(unused_tcp_port, "s4")

    assert mem.get_longterm("s4") == ""


@pytest.mark.asyncio
async def test_short_term_always_cleared_regardless_of_summary(unused_tcp_port):
    """Short-term memory is cleared whether or not summarization produces output."""
    mem = _mem()
    mem.update("s5", "any prompt", "any reply")
    assert mem.get("s5") != []

    with patch(
        "amxx_agent.core.handler.summarize_session",
        new=AsyncMock(return_value="- some summary"),
    ):
        srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
        async with srv:
            await _send_clear(unused_tcp_port, "s5")

    assert mem.get("s5") == []


@pytest.mark.asyncio
async def test_longterm_updated_not_replaced_on_second_clear(unused_tcp_port):
    """Subsequent clear_memory calls update long-term with the merged summary."""
    mem = _mem()
    mem.update("s6", "hello", "world")

    with patch(
        "amxx_agent.core.handler.summarize_session",
        new=AsyncMock(return_value="- first summary"),
    ):
        srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
        async with srv:
            await _send_clear(unused_tcp_port, "s6")

    assert mem.get_longterm("s6") == "- first summary"

    mem.update("s6", "second prompt", "second reply")

    with patch(
        "amxx_agent.core.handler.summarize_session",
        new=AsyncMock(return_value="- merged summary"),
    ) as mock_summarize:
        srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
        async with srv:
            await _send_clear(unused_tcp_port, "s6")

    assert mem.get_longterm("s6") == "- merged summary"
    # Prior summary was passed in for merging
    prior_arg = mock_summarize.call_args[0][1]
    assert prior_arg == "- first summary"
