# Examples

All example plugins compile as part of CI (see `.github/workflows/ci.yml`).
The compiled `.amxx` files are uploaded as a CI artifact but are **not**
included in releases - only `core.amxx` is released.

---

## weapon_advisor/

Per-player weapon advice backed by an AMX Mod X skill.

Demonstrates:
- `genai_register_skill` - gives the AI a loaded skill directory
- `genai_register_tool` + `genai_add_tool_param` - custom `get_my_weapon` tool
- `genai_query_player` with `this_plugin=true` - per-player isolated memory
- `genai_is_pending` - guard against duplicate requests
- `genai_clear_memory` - clear memory on player disconnect

The skill directory is included at `weapon_advisor/skills/weapon_advisor__cs16-strategy/`.
Deploy it to `GENAI_SKILLS_PATH` on the sidecar host before starting it.

---

## admin_assistant/

Admin-only AI assistant (`ADMIN_KICK` flag required) with persistent per-admin memory.

Demonstrates:
- `genai_set_plugin_context` + `genai_append_plugin_context` - build system prompt at init
- `genai_register_tool` + `genai_add_tool_param` - `get_server_stats` (no params) and `set_motd` (with param)
- `genai_register_skill` - loads `admin-procedures` skill
- `genai_query_player` with `this_plugin=true` - per-admin isolated memory
- `genai_is_pending` - guard against duplicate requests
- `genai_cancel` - `/ai_cancel` command cancels in-flight query
- `genai_clear_memory` - `/ai_reset` wipes short-term memory (triggers summarization)
- `genai_clear_longterm_memory` - `amx_ai_fullreset` discards the long-term summary entirely
- Access control via `get_user_flags`
- Splitting long AI responses across multiple chat lines

The skill directory is at `admin_assistant/skills/admin_assistant__admin-procedures/`.

---

## testable/

Example plugin designed for end-to-end integration testing. It is intentionally
observable: every AI response and tool call is written to the AMX log via `log_amx`.

Exercises all plugin API natives so integration tests can verify each one over the
wire without running a real game server:

| Native | How it is exercised |
|--------|---------------------|
| `genai_set_plugin_context` | Called in `plugin_init` |
| `genai_append_plugin_context` | Appended in `plugin_init` |
| `genai_register_tool` / `genai_add_tool_param` | Four tools with typed params |
| `genai_register_skill` | Registers `testable-knowledge` skill |
| `genai_query` | `say /test_ask` - server-scoped session |
| `genai_query_player` | `say /test_ask_player` - player-scoped session |
| `genai_is_pending` | Checked before every query; also exposed via `get_pending` tool |
| `genai_cancel` | `say /test_cancel` |
| `genai_clear_memory` | `say /test_clear` |
| `genai_clear_longterm_memory` | `say /test_clear_longterm` |

Tools the AI can call:

| Tool | Description |
|------|-------------|
| `get_log` | Returns all internal log entries as a JSON array |
| `set_value` | Stores a key-value pair |
| `get_value` | Reads a stored key-value pair |
| `get_pending` | Returns whether the server session has an in-flight query |

The matching integration test is at `tests/integration/test_example_testable.py`.
The skill directory is at `testable/skills/ai_testable__testable-knowledge/`.

---

See [docs/plugin-api.md](../docs/plugin-api.md) for the full native reference.
