"""Resolve Strands AgentSkills from registered skill names and built-in skill directories."""

import logging
from pathlib import Path

from strands import AgentSkills

from amxmodx_genai.config import settings

log = logging.getLogger(__name__)

# Sidecar-bundled skills live next to this file.
_BUILTIN_SKILLS_DIR = Path(__file__).parent


def load_plugin_skills(skill_names: list[str]) -> AgentSkills | None:
    """Return an AgentSkills plugin for the requested skill names.

    Each name is resolved against GENAI_SKILLS_PATH. Missing skills are logged
    and skipped so a bad name never aborts the whole query.
    """
    dirs: list[Path] = []
    for name in skill_names:
        path = settings.skills_path / name
        if (path / "SKILL.md").exists():
            dirs.append(path)
        else:
            log.warning("skill %r not found at %s", name, path)

    if not dirs:
        return None
    try:
        return AgentSkills(skills=[str(d) for d in dirs])
    except Exception as exc:
        log.warning("failed to construct AgentSkills for %s: %s", skill_names, exc)
        return None


def load_builtin_skills() -> AgentSkills | None:
    """Return an AgentSkills plugin for all skills bundled with the sidecar.

    Scans for subdirectories of src/amxmodx_genai/skills/ that contain a SKILL.md.
    Returns None when no built-in skills exist.
    """
    dirs = [d for d in _BUILTIN_SKILLS_DIR.iterdir() if d.is_dir() and (d / "SKILL.md").exists()]
    if not dirs:
        return None
    return AgentSkills(skills=[str(d) for d in dirs])
