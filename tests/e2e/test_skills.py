"""Tests for skill loading and injection via the handler."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.e2e.conftest import get_handle, make_agent_result, tcp_exchange


@pytest.mark.asyncio
async def test_plugin_skills_passed_to_agent(unused_tcp_port, tmp_path):
    """Skills requested in the query are loaded and passed as Agent plugins."""
    skill_dir = tmp_path / "myskill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# My Skill")

    captured_kwargs: dict = {}
    mock_agent_skills = MagicMock()

    def capture_agent(**kwargs):
        captured_kwargs.update(kwargs)
        inst = MagicMock()
        inst.invoke_async = AsyncMock(return_value=make_agent_result("ok"))
        return inst

    with (
        patch("amxmodx_genai.core.handler.Agent", side_effect=capture_agent),
        patch("amxmodx_genai.skills.loader.settings") as mock_settings,
        patch("amxmodx_genai.skills.loader.AgentSkills", return_value=mock_agent_skills),
    ):
        mock_settings.skills_path = tmp_path
        srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
        async with srv:
            await tcp_exchange(
                "127.0.0.1",
                unused_tcp_port,
                {
                    "type": "query",
                    "player": 1,
                    "prompt": "help",
                    "tools": [],
                    "skills": ["myskill"],
                },
            )

    assert "plugins" in captured_kwargs
    assert mock_agent_skills in captured_kwargs["plugins"]


@pytest.mark.asyncio
async def test_unknown_skill_skipped_query_still_succeeds(unused_tcp_port, tmp_path):
    """A query referencing a non-existent skill still completes successfully."""
    captured_kwargs: dict = {}

    def capture_agent(**kwargs):
        captured_kwargs.update(kwargs)
        inst = MagicMock()
        inst.invoke_async = AsyncMock(return_value=make_agent_result("ok"))
        return inst

    with (
        patch("amxmodx_genai.core.handler.Agent", side_effect=capture_agent),
        patch("amxmodx_genai.skills.loader.settings") as mock_settings,
    ):
        mock_settings.skills_path = tmp_path
        srv = await asyncio.start_server(get_handle(), "127.0.0.1", unused_tcp_port)
        async with srv:
            frames = await tcp_exchange(
                "127.0.0.1",
                unused_tcp_port,
                {
                    "type": "query",
                    "player": 1,
                    "prompt": "help",
                    "tools": [],
                    "skills": ["ghost_skill"],
                },
            )

    types = [f["type"] for f in frames]
    assert "response" in types
    assert "done" in types
    assert not captured_kwargs.get("plugins")
