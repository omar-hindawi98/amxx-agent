# ADR 003: Plugin naming convention for tools and skills

## Status

Accepted

## Context

Multiple AMXMODX plugins can be loaded simultaneously. Each plugin registers its own tools and skills. Without namespacing, two plugins registering a tool named `"get_map"` or a skill named `"strategy"` would collide.

A global registry with collision detection would fail on duplicate names and force plugin authors to manually choose unique names - error-prone and adds coordination burden across unrelated plugins. Plugin-author-supplied prefixes are flexible but inconsistent.

## Decision

Both `genai_register_tool` and `genai_register_skill` automatically prefix the registered name with the calling plugin's filename (minus `.amxx`) and a double underscore separator.

- `genai_register_tool("get_map", ...)` in `my_coach.amxx` -> agent sees `my_coach__get_map`
- `genai_register_skill("strategy")` in `my_coach.amxx` -> loaded as `my_coach__strategy`

The SKILL.md `name` field must match the directory name, which uses the same prefixed form.

## Consequences

- Plugin authors never think about namespacing; collisions are structurally impossible.
- The agent sees prefixed names in tool descriptions, which is slightly verbose but unambiguous.
- Renaming a plugin file changes all its tool and skill names. This is intentional - the name is tied to the plugin identity.
