"""Skills loader.

Plugin-registered skills are loaded from GENAI_SKILLS_PATH/<name>/SKILL.md.
Sidecar built-in skills live in src/amxmodx_genai/skills/<name>/SKILL.md.
"""

from amxmodx_genai.skills.loader import load_builtin_skills, load_plugin_skills

__all__ = ["load_builtin_skills", "load_plugin_skills"]
