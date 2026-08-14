"""Tests for skill loading and injection via the handler."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.integration.conftest import requires_ollama
from tests.integration.helpers import get_handle, make_agent_result, tcp_exchange


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


# ---------------------------------------------------------------------------
# Multiple skills: both paths passed to AgentSkills
# ---------------------------------------------------------------------------


@requires_ollama
@pytest.mark.asyncio
async def test_multiple_skills_both_passed_to_agent_skills(unused_tcp_port, tmp_path):
    """Both skill directories are included when two skills are requested."""
    skill_a = tmp_path / "skill_alpha"
    skill_a.mkdir()
    (skill_a / "SKILL.md").write_text("# Alpha")

    skill_b = tmp_path / "skill_beta"
    skill_b.mkdir()
    (skill_b / "SKILL.md").write_text("# Beta")

    captured_skills_calls: list[list[str]] = []

    def fake_agent_skills(**kwargs):
        captured_skills_calls.append(kwargs.get("skills", []))
        return MagicMock()

    with (
        patch("amxmodx_genai.skills.loader.settings") as mock_settings,
        patch("amxmodx_genai.skills.loader.AgentSkills", side_effect=fake_agent_skills),
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
                    "skills": ["skill_alpha", "skill_beta"],
                },
            )

    assert len(captured_skills_calls) == 1
    paths = captured_skills_calls[0]
    assert any("skill_alpha" in p for p in paths)
    assert any("skill_beta" in p for p in paths)


# ---------------------------------------------------------------------------
# Skill directory path: AgentSkills receives the exact path we registered
# ---------------------------------------------------------------------------


@requires_ollama
@pytest.mark.asyncio
async def test_skill_directory_path_passed_to_agent_skills(unused_tcp_port, tmp_path):
    """The path passed to AgentSkills is the exact directory containing SKILL.md."""
    skill_dir = tmp_path / "myskill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# My Skill\nDo things.")

    captured_paths: list[list[str]] = []

    def fake_agent_skills(**kwargs):
        captured_paths.append(kwargs.get("skills", []))
        return MagicMock()

    with (
        patch("amxmodx_genai.skills.loader.settings") as mock_settings,
        patch("amxmodx_genai.skills.loader.AgentSkills", side_effect=fake_agent_skills),
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

    assert len(captured_paths) == 1
    assert len(captured_paths[0]) == 1
    assert captured_paths[0][0] == str(skill_dir)


# ---------------------------------------------------------------------------
# Partial skill list: only found skills passed, missing one silently dropped
# ---------------------------------------------------------------------------


@requires_ollama
@pytest.mark.asyncio
async def test_partial_skill_list_passes_only_found_skills(unused_tcp_port, tmp_path):
    """When one of two requested skills is missing, only the found one is passed."""
    skill_dir = tmp_path / "real_skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Real")

    captured_paths: list[list[str]] = []

    def fake_agent_skills(**kwargs):
        captured_paths.append(kwargs.get("skills", []))
        return MagicMock()

    with (
        patch("amxmodx_genai.skills.loader.settings") as mock_settings,
        patch("amxmodx_genai.skills.loader.AgentSkills", side_effect=fake_agent_skills),
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
                    "skills": ["real_skill", "ghost_skill"],
                },
            )

    types = [f["type"] for f in frames]
    assert "response" in types
    assert len(captured_paths) == 1
    assert len(captured_paths[0]) == 1
    assert "real_skill" in captured_paths[0][0]


@pytest.mark.asyncio
async def test_agent_skills_constructor_raises_query_still_succeeds(unused_tcp_port, tmp_path):
    """When AgentSkills() raises during construction, the query completes without plugins."""
    skill_dir = tmp_path / "badskill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Bad Skill")

    captured_kwargs: dict = {}

    def capture_agent(**kwargs):
        captured_kwargs.update(kwargs)
        inst = MagicMock()
        inst.invoke_async = AsyncMock(return_value=make_agent_result("ok"))
        return inst

    def raising_skills(**kwargs):
        raise RuntimeError("corrupted skill file")

    with (
        patch("amxmodx_genai.core.handler.Agent", side_effect=capture_agent),
        patch("amxmodx_genai.skills.loader.settings") as mock_settings,
        patch("amxmodx_genai.skills.loader.AgentSkills", side_effect=raising_skills),
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
                    "skills": ["badskill"],
                },
            )

    types = [f["type"] for f in frames]
    assert "response" in types
    assert "done" in types
