"""Skills loader.

Plugin-registered skills are loaded from AGENT_SKILLS_PATH/<name>/SKILL.md.
Sidecar built-in skills live in src/amxx_agent/skills/<name>/SKILL.md.
"""

from amxx_agent.skills.loader import load_builtin_skills, load_plugin_skills

__all__ = ["load_builtin_skills", "load_plugin_skills"]
