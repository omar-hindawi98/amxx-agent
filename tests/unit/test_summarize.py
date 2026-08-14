"""Unit tests for core/summarize.py - prompt construction and early exits."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _get_summarize():
    from amxmodx_genai.core.summarize import summarize_session

    return summarize_session


def _make_history(*turns: tuple[str, str]) -> list[dict]:
    """Build a minimal message history from (role, text) pairs."""
    return [{"role": role, "content": [{"type": "text", "text": text}]} for role, text in turns]


def _mock_agent_result(text: str) -> MagicMock:
    result = MagicMock()
    result.message = {"content": [{"type": "text", "text": text}]}
    return result


# ---------------------------------------------------------------------------
# Early-exit: no text turns
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_history_returns_empty_string():
    result = await _get_summarize()([], prior_summary="")
    assert result == ""


@pytest.mark.asyncio
async def test_history_with_no_text_blocks_returns_empty_string():
    history = [{"role": "user", "content": [{"type": "image", "url": "x"}]}]
    result = await _get_summarize()(history, prior_summary="")
    assert result == ""


# ---------------------------------------------------------------------------
# Prompt construction - fresh summary (no prior)
# ---------------------------------------------------------------------------


_AGENT_PATH = "amxmodx_genai.core.summarize.Agent"
_MODEL_PATH = "amxmodx_genai.core.summarize.get_summary_model"


@pytest.mark.asyncio
async def test_fresh_summary_prompt_contains_conversation():
    history = _make_history(("user", "hello"), ("assistant", "hi there"))
    captured_prompt = []

    mock_result = _mock_agent_result("- greeted user")
    mock_agent = MagicMock()

    async def fake_invoke(prompt):
        captured_prompt.append(prompt)
        return mock_result

    mock_agent.invoke_async = fake_invoke

    with patch(_AGENT_PATH, return_value=mock_agent), patch(_MODEL_PATH, return_value=MagicMock()):
        result = await _get_summarize()(history, prior_summary="")

    assert "user: hello" in captured_prompt[0]
    assert "assistant: hi there" in captured_prompt[0]
    assert "Prior summary" not in captured_prompt[0]
    assert result == "- greeted user"


# ---------------------------------------------------------------------------
# Prompt construction - merge with prior summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_merge_prompt_includes_prior_summary():
    history = _make_history(("user", "new info"))
    captured_prompt = []

    mock_result = _mock_agent_result("- updated summary")
    mock_agent = MagicMock()

    async def fake_invoke(prompt):
        captured_prompt.append(prompt)
        return mock_result

    mock_agent.invoke_async = fake_invoke

    with patch(_AGENT_PATH, return_value=mock_agent), patch(_MODEL_PATH, return_value=MagicMock()):
        result = await _get_summarize()(history, prior_summary="Old stuff")

    assert "Prior summary" in captured_prompt[0]
    assert "Old stuff" in captured_prompt[0]
    assert "user: new info" in captured_prompt[0]
    assert result == "- updated summary"


# ---------------------------------------------------------------------------
# Result extraction - handles attribute-based message (non-dict)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_result_with_attribute_based_message():
    history = _make_history(("user", "test"))

    content_block = MagicMock()
    content_block.text = "attr-based result"

    msg = MagicMock()
    msg.content = [content_block]
    mock_result = MagicMock()
    mock_result.message = msg

    mock_agent = MagicMock()
    mock_agent.invoke_async = AsyncMock(return_value=mock_result)

    with patch(_AGENT_PATH, return_value=mock_agent), patch(_MODEL_PATH, return_value=MagicMock()):
        result = await _get_summarize()(history, prior_summary="")

    assert result == "attr-based result"
