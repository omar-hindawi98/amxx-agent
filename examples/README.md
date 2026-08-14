# Examples

All example plugins compile as part of CI (see `.github/workflows/ci.yml`).
The compiled `.amxx` files are uploaded as a CI artifact but are **not**
included in releases - only `core.amxx` is released.

---

## weapon_advisor/

Per-player weapon advice backed by an AMX Mod X skill.

Demonstrates:
- `genai_register_skill` - gives the AI a loaded skill directory without embedding knowledge in the plugin
- A custom tool (`get_my_weapon`) alongside the skill
- Per-player memory isolated to this plugin (`this_plugin=true`)

Requires the `cs16-strategy` skill directory to be present at
`GENAI_SKILLS_PATH/weapon_advisor__cs16-strategy/` on the sidecar host
(see `skills/cs16-strategy/` in this directory).

---

## admin_assistant/

Admin-only AI assistant (`ADMIN_KICK` flag required) with persistent per-admin
conversation memory and access to core server tools (get_players, kick, ban, etc.).

Demonstrates:
- Access control via `get_user_flags`
- `genai_set_plugin_context` + `genai_append_plugin_context` together
- `genai_clear_memory` via an explicit `/ai_reset` command
- Splitting long AI responses across multiple chat lines

---

## testable/

Example plugin designed for end-to-end integration testing. It is intentionally
observable: every AI response and tool call is written to the AMX log via `log_amx`
and an internal log that the AI can read back.

The plugin uses fixed session `"testable"` so Python tests can target it directly
over TCP without running a real game server. It exposes three tools:

| Tool | Description |
|------|-------------|
| `get_log` | Returns all internal log entries as a JSON array |
| `set_value` | Stores a key-value pair the AI can write back into game state |
| `get_value` | Reads a stored key-value pair |

The matching integration test is at
`tests/integration/test_example_testable.py`.

---

## skills/cs16-strategy/

Example skill directory. Copy to `GENAI_SKILLS_PATH/<plugin>__cs16-strategy/`
on the sidecar host, then register from the plugin with:

```pawn
genai_register_skill("cs16-strategy");
```

See [docs/plugin-api.md](../docs/plugin-api.md) for the full native reference.
