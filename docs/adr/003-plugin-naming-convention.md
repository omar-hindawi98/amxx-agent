# ADR 003: Plugin naming convention for tools and skills

## Status

Accepted

## Context

Multiple AMX Mod X plugins can be loaded simultaneously. Each plugin registers its own tools and skills. Without namespacing, two plugins registering a tool named `"get_map"` or a skill named `"strategy"` would collide.

A global registry with collision detection would fail on duplicate names and force plugin authors to manually choose unique names - error-prone and adds coordination burden across unrelated plugins. Plugin-author-supplied prefixes are flexible but inconsistent.

## Decision

Both `genai_register_tool` and `genai_register_skill` automatically prefix the registered name with the calling plugin's filename (minus `.amxx`) and a double underscore separator.

- `genai_register_tool("get_map", ...)` in `my_coach.amxx` -> agent sees `my_coach__get_map`
- `genai_register_skill("strategy")` in `my_coach.amxx` -> loaded as `my_coach__strategy`

The SKILL.md `name` field must match the directory name, which uses the same prefixed form.

## Alternatives Considered

- **Manual prefixes by plugin authors** - flexible but error-prone; relies on authors knowing what other plugins exist and consistently applying a convention.
- **Global registry with collision detection** - fails loudly on duplicate names, forcing plugin authors to coordinate across unrelated plugins; adds runtime error paths.
- **UUID-based tool IDs** - collision-proof but opaque; the agent sees meaningless names and cannot use them meaningfully in reasoning.
- **Namespaced objects per plugin** - keeps each plugin's tools isolated but requires a more complex API surface and changes how the agent addresses tools.

## Consequences

- Plugin authors never think about namespacing; collisions are structurally impossible.
- The agent sees prefixed names in tool descriptions, which is slightly verbose but unambiguous.
- Renaming a plugin file changes all its tool and skill names. This is intentional - the name is tied to the plugin identity.
