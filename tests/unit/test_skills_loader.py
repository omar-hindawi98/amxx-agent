"""Unit tests for skills/loader.py - path resolution and SKILL.md detection."""

from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_skill_dir(tmp_path: Path, name: str, *, with_skill_md: bool = True) -> Path:
    d = tmp_path / name
    d.mkdir()
    if with_skill_md:
        (d / "SKILL.md").write_text("# skill")
    return d


# ---------------------------------------------------------------------------
# load_plugin_skills
# ---------------------------------------------------------------------------


def test_load_plugin_skills_valid(tmp_path):
    _make_skill_dir(tmp_path, "greet")
    import amxx_agent.skills.loader as loader

    mock_agent_skills = MagicMock()
    with patch("amxx_agent.skills.loader.settings") as mock_settings:
        mock_settings.skills_path = tmp_path
        with patch("amxx_agent.skills.loader.AgentSkills", mock_agent_skills):
            loader.load_plugin_skills(["greet"])

    mock_agent_skills.assert_called_once()
    dirs_arg = mock_agent_skills.call_args.kwargs["skills"]
    assert any("greet" in d for d in dirs_arg)


def test_load_plugin_skills_missing_skill_is_skipped(tmp_path, caplog):
    _make_skill_dir(tmp_path, "real")
    import logging

    import amxx_agent.skills.loader as loader

    mock_agent_skills = MagicMock()
    with patch("amxx_agent.skills.loader.settings") as mock_settings:
        mock_settings.skills_path = tmp_path
        with (
            patch("amxx_agent.skills.loader.AgentSkills", mock_agent_skills),
            caplog.at_level(logging.WARNING),
        ):
            loader.load_plugin_skills(["real", "ghost"])

    # Only "real" should be passed; "ghost" logged and skipped.
    dirs_arg = mock_agent_skills.call_args.kwargs["skills"]
    assert len(dirs_arg) == 1
    assert "real" in dirs_arg[0]
    assert any("ghost" in r.message for r in caplog.records)


def test_load_plugin_skills_all_missing_returns_none(tmp_path):
    import amxx_agent.skills.loader as loader

    with patch("amxx_agent.skills.loader.settings") as mock_settings:
        mock_settings.skills_path = tmp_path
        with patch("amxx_agent.skills.loader.AgentSkills", MagicMock()):
            result = loader.load_plugin_skills(["nonexistent"])

    assert result is None


def test_load_plugin_skills_empty_list_returns_none(tmp_path):
    import amxx_agent.skills.loader as loader

    with patch("amxx_agent.skills.loader.settings") as mock_settings:
        mock_settings.skills_path = tmp_path
        with patch("amxx_agent.skills.loader.AgentSkills", MagicMock()):
            result = loader.load_plugin_skills([])

    assert result is None


# ---------------------------------------------------------------------------
# load_builtin_skills
# ---------------------------------------------------------------------------


def test_load_builtin_skills_finds_skill_md_dirs(tmp_path):
    _make_skill_dir(tmp_path, "builtin_a")
    _make_skill_dir(tmp_path, "builtin_b")
    _make_skill_dir(tmp_path, "no_skill_md", with_skill_md=False)

    mock_agent_skills = MagicMock()
    import amxx_agent.skills.loader as loader

    with (
        patch.object(loader, "_BUILTIN_SKILLS_DIR", tmp_path),
        patch("amxx_agent.skills.loader.AgentSkills", mock_agent_skills),
    ):
        loader.load_builtin_skills()

    dirs_arg = mock_agent_skills.call_args.kwargs["skills"]
    names = {Path(d).name for d in dirs_arg}
    assert "builtin_a" in names
    assert "builtin_b" in names
    assert "no_skill_md" not in names


def test_load_builtin_skills_no_dirs_returns_none(tmp_path):
    import amxx_agent.skills.loader as loader

    with patch.object(loader, "_BUILTIN_SKILLS_DIR", tmp_path):
        result = loader.load_builtin_skills()

    assert result is None
