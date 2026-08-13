"""Unit tests for handler internals: _shift_headings, _build_system_prompt, content extraction."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.integration.helpers import make_agent_result


def _get_handler():
    import amxmodx_genai.core.handler as h

    return h


# ---------------------------------------------------------------------------
# _shift_headings
# ---------------------------------------------------------------------------


def test_shift_headings_single():
    h = _get_handler()
    assert h._shift_headings("# Title") == "### Title"


def test_shift_headings_all_levels():
    h = _get_handler()
    text = "# H1\n## H2\n### H3\n#### H4\n##### H5\n###### H6"
    result = h._shift_headings(text)
    assert result == "### H1\n#### H2\n##### H3\n###### H4\n###### H5\n###### H6"


def test_shift_headings_caps_at_six():
    h = _get_handler()
    # Level 5 and 6 should both cap at 6
    assert h._shift_headings("##### Five") == "###### Five"
    assert h._shift_headings("###### Six") == "###### Six"


def test_shift_headings_no_space_not_treated_as_heading():
    h = _get_handler()
    # "#Nospace" should not be shifted
    assert h._shift_headings("#Nospace") == "#Nospace"


def test_shift_headings_empty_string():
    h = _get_handler()
    assert h._shift_headings("") == ""


def test_shift_headings_no_headings():
    h = _get_handler()
    text = "Just plain text\nno headings here"
    assert h._shift_headings(text) == text


def test_shift_headings_multiline():
    h = _get_handler()
    text = "# A\nsome text\n## B"
    result = h._shift_headings(text)
    assert result == "### A\nsome text\n#### B"


# ---------------------------------------------------------------------------
# _build_system_prompt
# ---------------------------------------------------------------------------


def test_build_system_prompt_base_only():
    h = _get_handler()
    result = h._build_system_prompt("", "", "")
    assert result == h._BASE_SYSTEM_PROMPT


def test_build_system_prompt_with_longterm():
    h = _get_handler()
    result = h._build_system_prompt("", "", "- Player prefers rifles")
    assert "Memory from previous sessions" in result
    assert "Player prefers rifles" in result


def test_build_system_prompt_with_plugin_context():
    h = _get_handler()
    result = h._build_system_prompt("myplugin", "# Rules\nDo stuff", "")
    assert "## myplugin" in result
    assert "### Rules" in result
    assert "Do stuff" in result


def test_build_system_prompt_unnamed_plugin():
    h = _get_handler()
    result = h._build_system_prompt("", "Some context", "")
    assert "## Plugin context" in result
    assert "Some context" in result


def test_build_system_prompt_all_three():
    h = _get_handler()
    result = h._build_system_prompt("myplugin", "# Rules", "- fact")
    assert "Memory from previous sessions" in result
    assert "- fact" in result
    assert "## myplugin" in result
    assert "### Rules" in result


def test_build_system_prompt_plugin_headings_nested():
    # Headings inside plugin_context must be shifted so they sit below ## plugin
    h = _get_handler()
    result = h._build_system_prompt("p", "# Top\n## Sub", "")
    assert "### Top" in result
    assert "#### Sub" in result
    # Original bare heading chars should not appear at those levels
    assert "\n# Top" not in result
    assert "\n## Sub" not in result


# ---------------------------------------------------------------------------
# Content extraction from agent result
# ---------------------------------------------------------------------------


def _make_frames_from_send(captured: list[dict]):
    """Return frames list from captured sends."""
    return captured


@pytest.mark.asyncio
async def test_empty_content_list_returns_no_response(unused_tcp_port):
    """Agent result with empty content list produces '(no response)'."""
    from tests.integration.helpers import get_handle, tcp_exchange

    result = MagicMock()
    msg = MagicMock()
    msg.content = []
    result.message = msg

    def make_agent(**kwargs):
        inst = MagicMock()
        inst.invoke_async = AsyncMock(return_value=result)
        return inst

    with patch("amxmodx_genai.core.handler.Agent", side_effect=make_agent):
        srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
        async with srv:
            frames = await tcp_exchange(
                "127.0.0.1",
                unused_tcp_port,
                {"type": "query", "player": 1, "prompt": "hello", "tools": []},
            )

    response = next(f for f in frames if f["type"] == "response")
    assert response["text"] == "(no response)"


@pytest.mark.asyncio
async def test_whitespace_only_text_returns_no_response(unused_tcp_port):
    """Agent result with only whitespace text produces '(no response)'."""
    from tests.integration.helpers import get_handle, tcp_exchange

    block = MagicMock()
    block.text = "\n\n   \n"
    msg = MagicMock()
    msg.content = [block]
    result = MagicMock()
    result.message = msg

    def make_agent(**kwargs):
        inst = MagicMock()
        inst.invoke_async = AsyncMock(return_value=result)
        return inst

    with patch("amxmodx_genai.core.handler.Agent", side_effect=make_agent):
        srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
        async with srv:
            frames = await tcp_exchange(
                "127.0.0.1",
                unused_tcp_port,
                {"type": "query", "player": 1, "prompt": "hello", "tools": []},
            )

    response = next(f for f in frames if f["type"] == "response")
    assert response["text"] == "(no response)"


@pytest.mark.asyncio
async def test_none_message_returns_no_response(unused_tcp_port):
    """Agent result with message=None produces '(no response)'."""
    from tests.integration.helpers import get_handle, tcp_exchange

    result = MagicMock()
    result.message = None

    def make_agent(**kwargs):
        inst = MagicMock()
        inst.invoke_async = AsyncMock(return_value=result)
        return inst

    with patch("amxmodx_genai.core.handler.Agent", side_effect=make_agent):
        srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
        async with srv:
            frames = await tcp_exchange(
                "127.0.0.1",
                unused_tcp_port,
                {"type": "query", "player": 1, "prompt": "hello", "tools": []},
            )

    response = next(f for f in frames if f["type"] == "response")
    assert response["text"] == "(no response)"


@pytest.mark.asyncio
async def test_dict_content_block_text_extracted(unused_tcp_port):
    """Agent result with dict-style content blocks (not MagicMock) extracts text correctly."""
    from tests.integration.helpers import get_handle, tcp_exchange

    result = MagicMock()
    result.message = {"content": [{"type": "text", "text": "dict response"}]}

    def make_agent(**kwargs):
        inst = MagicMock()
        inst.invoke_async = AsyncMock(return_value=result)
        return inst

    with patch("amxmodx_genai.core.handler.Agent", side_effect=make_agent):
        srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
        async with srv:
            frames = await tcp_exchange(
                "127.0.0.1",
                unused_tcp_port,
                {"type": "query", "player": 1, "prompt": "hello", "tools": []},
            )

    response = next(f for f in frames if f["type"] == "response")
    assert response["text"] == "dict response"


# ---------------------------------------------------------------------------
# clear_memory: summarization failure still clears short-term memory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_memory_still_clears_when_summarization_fails(unused_tcp_port):
    """If summarize_session raises, short-term memory is still cleared."""

    import amxmodx_genai.core.memory as mem

    mem.update("99", "hello", "world")
    assert mem.get("99") != []

    async def failing_summarize(*args, **kwargs):
        raise RuntimeError("LLM is down")

    with patch("amxmodx_genai.core.handler.summarize_session", side_effect=failing_summarize):
        from amxmodx_genai.server import handle_once

        srv = await asyncio.start_server(handle_once, "127.0.0.1", unused_tcp_port)
        async with srv:
            import json

            reader, writer = await asyncio.open_connection("127.0.0.1", unused_tcp_port)
            writer.write(
                (
                    json.dumps({"type": "clear_memory", "player": 99, "session_id": "99"}) + "\n"
                ).encode()
            )
            await writer.drain()
            await asyncio.sleep(0.3)
            writer.close()
            await writer.wait_closed()

    assert mem.get("99") == []


@pytest.mark.asyncio
async def test_clear_memory_longterm_not_updated_when_summarization_fails(unused_tcp_port):
    """If summarize_session raises, long-term memory is not updated."""
    import amxmodx_genai.core.memory as mem

    mem.update("100", "hello", "world")
    mem.set_longterm("100", "existing summary")

    async def failing_summarize(*args, **kwargs):
        raise RuntimeError("LLM is down")

    with patch("amxmodx_genai.core.handler.summarize_session", side_effect=failing_summarize):
        from amxmodx_genai.server import handle_once

        srv = await asyncio.start_server(handle_once, "127.0.0.1", unused_tcp_port)
        async with srv:
            import json

            reader, writer = await asyncio.open_connection("127.0.0.1", unused_tcp_port)
            writer.write(
                (
                    json.dumps({"type": "clear_memory", "player": 100, "session_id": "100"}) + "\n"
                ).encode()
            )
            await writer.drain()
            await asyncio.sleep(0.3)
            writer.close()
            await writer.wait_closed()

    # Short-term cleared but long-term unchanged
    assert mem.get("100") == []
    assert mem.get_longterm("100") == "existing summary"


# ---------------------------------------------------------------------------
# _safe_send_error: broken send callable does not propagate exceptions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_safe_send_error_suppresses_send_exception():
    """_safe_send_error suppresses exceptions raised by the send callable."""
    import amxmodx_genai.core.handler as h

    async def broken_send(obj: dict) -> None:
        raise OSError("socket closed")

    # Should not raise - all exceptions suppressed by contextlib.suppress
    await h._safe_send_error(broken_send, "(error message)")


@pytest.mark.asyncio
async def test_safe_send_error_suppresses_on_second_call():
    """_safe_send_error suppresses even if the second send (done) raises."""
    import amxmodx_genai.core.handler as h

    call_count = 0

    async def half_broken_send(obj: dict) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError("socket closed on done frame")

    await h._safe_send_error(half_broken_send, "(error message)")
    # First call succeeded; second raised - no exception should escape
    assert call_count >= 1


@pytest.mark.asyncio
async def test_handler_exception_uses_safe_send_error(unused_tcp_port):
    """When the agent raises unexpectedly, _safe_send_error delivers the error frame."""
    from tests.integration.helpers import get_handle, tcp_exchange

    def make_agent(**kwargs):
        inst = MagicMock()
        inst.invoke_async = AsyncMock(side_effect=RuntimeError("unexpected crash"))
        return inst

    with (
        patch("amxmodx_genai.core.handler.Agent", side_effect=make_agent),
        patch("amxmodx_genai.core.handler.asyncio.sleep", new=AsyncMock()),
    ):
        srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
        async with srv:
            frames = await tcp_exchange(
                "127.0.0.1",
                unused_tcp_port,
                {"type": "query", "player": 1, "prompt": "hello", "tools": []},
            )

    types = [f["type"] for f in frames]
    assert "response" in types
    assert "done" in types
    response = next(f for f in frames if f["type"] == "response")
    assert "unavailable" in response["text"].lower()


# ---------------------------------------------------------------------------
# Protocol frame ordering: response arrives before done
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_response_frame_arrives_before_done_frame(unused_tcp_port):
    """The response frame must always precede the done frame in the stream."""
    from tests.integration.helpers import get_handle, make_agent_result, tcp_exchange

    def make_agent(**kwargs):
        inst = MagicMock()
        inst.invoke_async = AsyncMock(return_value=make_agent_result("ordered response"))
        return inst

    with patch("amxmodx_genai.core.handler.Agent", side_effect=make_agent):
        srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
        async with srv:
            frames = await tcp_exchange(
                "127.0.0.1",
                unused_tcp_port,
                {"type": "query", "player": 1, "prompt": "hello", "tools": []},
            )

    types = [f["type"] for f in frames]
    assert "response" in types
    assert "done" in types
    assert types.index("response") < types.index("done"), (
        f"expected response before done, got ordering: {types}"
    )


@pytest.mark.asyncio
async def test_error_response_frame_arrives_before_done_frame(unused_tcp_port):
    """Even the error response path sends response before done."""
    from tests.integration.helpers import get_handle, tcp_exchange

    def make_agent(**kwargs):
        inst = MagicMock()
        inst.invoke_async = AsyncMock(side_effect=RuntimeError("boom"))
        return inst

    with (
        patch("amxmodx_genai.core.handler.Agent", side_effect=make_agent),
        patch("amxmodx_genai.core.handler.asyncio.sleep", new=AsyncMock()),
    ):
        srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
        async with srv:
            frames = await tcp_exchange(
                "127.0.0.1",
                unused_tcp_port,
                {"type": "query", "player": 1, "prompt": "hello", "tools": []},
            )

    types = [f["type"] for f in frames]
    assert types.index("response") < types.index("done"), (
        f"expected response before done on error path, got: {types}"
    )


# ---------------------------------------------------------------------------
# Semaphore: requests queue when max_concurrent is saturated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_semaphore_queues_requests_when_saturated(unused_tcp_port):
    """When max_concurrent=1, a second request queues and completes after the first."""
    import amxmodx_genai.server as srv_mod

    # Set semaphore to 1 so only one handler runs at a time
    original_sem = srv_mod._sem
    srv_mod._sem = asyncio.Semaphore(1)

    first_started = asyncio.Event()
    first_may_finish = asyncio.Event()
    completion_order: list[int] = []

    async def slow_invoke(prompt):
        first_started.set()
        await first_may_finish.wait()
        completion_order.append(1)
        return make_agent_result("first done")

    async def fast_invoke(prompt):
        completion_order.append(2)
        return make_agent_result("second done")

    call_count = 0

    def make_agent(**kwargs):
        nonlocal call_count
        call_count += 1
        n = call_count
        inst = MagicMock()
        inst.invoke_async = AsyncMock(side_effect=slow_invoke if n == 1 else fast_invoke)
        return inst

    with patch("amxmodx_genai.core.handler.Agent", side_effect=make_agent):
        from amxmodx_genai.server import handle_once

        srv = await asyncio.start_server(handle_once, "127.0.0.1", unused_tcp_port)
        async with srv:
            # Send first request and wait until its agent is running
            t1 = asyncio.create_task(_send_single("127.0.0.1", unused_tcp_port, "first"))
            await first_started.wait()

            # Send second request - it must queue behind the semaphore
            t2 = asyncio.create_task(_send_single("127.0.0.1", unused_tcp_port, "second"))
            # Small yield to let t2 reach the semaphore
            await asyncio.sleep(0.05)

            # Release the first
            first_may_finish.set()

            frames1, frames2 = await asyncio.gather(t1, t2)

    srv_mod._sem = original_sem

    # Both completed
    assert any(f["type"] == "response" for f in frames1)
    assert any(f["type"] == "response" for f in frames2)
    # First completed before second (semaphore forced serialization)
    assert completion_order == [1, 2], f"unexpected order: {completion_order}"


async def _send_single(host: str, port: int, label: str) -> list[dict]:
    """Helper: open connection, send one query, collect frames."""

    reader, writer = await asyncio.open_connection(host, port)
    writer.write(
        (json.dumps({"type": "query", "player": 1, "prompt": label, "tools": []}) + "\n").encode()
    )
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
