"""Tests for Agent invocation retry logic in the handler."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.integration.helpers import get_handle, make_agent_result, tcp_exchange


@pytest.mark.asyncio
async def test_invoke_retried_once_on_failure(unused_tcp_port):
    """A failing Agent invocation is retried once and succeeds on second attempt."""
    attempt_count = 0

    async def flaky_invoke(prompt):
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count == 1:
            raise RuntimeError("transient error")
        return make_agent_result("Recovered response.")

    def make_agent(**kwargs):
        inst = MagicMock()
        inst.invoke_async = AsyncMock(side_effect=flaky_invoke)
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

    assert attempt_count == 2
    response = next(f for f in frames if f["type"] == "response")
    assert "Recovered" in response["text"]


@pytest.mark.asyncio
async def test_invoke_fails_after_all_retries(unused_tcp_port):
    """When all retry attempts fail, handler returns an error response."""

    async def always_fail(prompt):
        raise RuntimeError("persistent error")

    def make_agent(**kwargs):
        inst = MagicMock()
        inst.invoke_async = AsyncMock(side_effect=always_fail)
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
