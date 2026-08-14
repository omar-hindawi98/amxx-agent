# AMX Mod X GenAI

<img src="docs/assets/logo.png" alt="AMX Mod X GenAI" width="200">

[![Release](https://img.shields.io/github/v/release/omar-hindawi98/amxmodx-genai)](https://github.com/omar-hindawi98/amxmodx-genai/releases)
[![AMX Mod X](https://img.shields.io/badge/AMX%20Mod%20X-1.8.2%2B-orange)](https://www.amxmodx.org/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

[![CI](https://img.shields.io/github/actions/workflow/status/omar-hindawi98/amxmodx-genai/ci.yml?branch=main&label=CI)](https://github.com/omar-hindawi98/amxmodx-genai/actions/workflows/ci.yml)
[![E2E](https://img.shields.io/github/actions/workflow/status/omar-hindawi98/amxmodx-genai/e2e.yml?branch=main&label=E2E)](https://github.com/omar-hindawi98/amxmodx-genai/actions/workflows/e2e.yml)

LLM agent bridge for AMX Mod X game servers. Plugins call simple Pawn natives; a local Python TCP sidecar runs a Strands agent loop against a configurable LLM backend with two-tier persistent memory, plugin-registered tools and skills, and a composable system prompt.

```mermaid
graph LR
    subgraph CS 1.6 server
        core["core.amxx"]
        plugin["your_plugin.amxx"]
    end
    sidecar["amxmodx_genai sidecar"]
    llm["LLM"]

    core <-->|"TCP protocol v2"| sidecar
    sidecar -->|HTTPS or local| llm
```

## Requirements

- [AMX Mod X Sockets](https://www.amxmodx.org/sc/sockets.php) module
- [uv](https://docs.astral.sh/uv/)

## Installation

### Sidecar

```sh
uv sync
GENAI_MODEL_API_KEY=sk-ant-... uv run genai-sidecar
```

Use Ollama as the local LLM backend:

```sh
GENAI_MODEL_BACKEND=ollama GENAI_MODEL_NAME=llama3.2 uv run genai-sidecar
```

### AMX Mod X plugin

1. Compile `plugins/amxmodx_genai/core.sma` and copy `core.amxx` to `addons/amxmodx/plugins/`.
2. Copy `plugins/include/amxmodx_genai.inc` to `addons/amxmodx/scripting/include/`.
3. Add `core.amxx` before your plugin in `addons/amxmodx/configs/plugins.ini`.

## Configuration

### CVars (game server)

| CVar                | Default     | Description                               |
| ------------------- | ----------- | ----------------------------------------- |
| `genai_host`        | `127.0.0.1` | Sidecar host                              |
| `genai_port`        | `27016`     | Sidecar port                              |
| `genai_core_tools`  | `1`         | Enable built-in sidecar tools             |
| `genai_core_skills` | `1`         | Enable built-in `amxmodx-reference` skill |

### Environment variables (sidecar)

| Variable                        | Default                                  | Description                                                                                                                                                            |
| ------------------------------- | ---------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GENAI_HOST`                    | `127.0.0.1`                              | Bind address                                                                                                                                                           |
| `GENAI_PORT`                    | `27016`                                  | Bind port                                                                                                                                                              |
| `GENAI_MAX_CONCURRENT`          | `32`                                     | Maximum simultaneous in-flight requests                                                                                                                                |
| `GENAI_REQUEST_TIMEOUT_SECONDS` | `60`                                     | Per-request LLM timeout in seconds. Set to `0` to disable.                                                                                                             |
| `GENAI_AUTH_TOKEN`              | ``                                       | When non-empty, every `query` and `clear_memory` message must include a matching `auth_token` field or the request is rejected. Leave empty to disable auth (default). |
| `GENAI_LOG_LEVEL`               | `INFO`                                   | Log verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR`                                                                                                                     |
| `GENAI_MODEL_BACKEND`           | `ollama`                                 | LLM backend: `anthropic`, `bedrock`, `ollama`, `litellm`, or `openai`                                                                                                  |
| `GENAI_MODEL_NAME`              | `llama3.2:1b`                            | Model ID passed to the backend                                                                                                                                         |
| `GENAI_MODEL_TOKENS`            | `2048`                                   | `max_tokens` per response                                                                                                                                              |
| `GENAI_MODEL_API_KEY`           | ``                                       | API key for `anthropic`, `openai`, and `litellm` backends                                                                                                              |
| `GENAI_MODEL_ENDPOINT`          | ``                                       | Custom endpoint URL (Ollama: `http://localhost:11434`, OpenAI-compatible proxies, etc.)                                                                                |
| `GENAI_MEMORY_PATH`             | `~/.local/share/amxmodx_genai/memory.db` | SQLite memory file                                                                                                                                                     |
| `GENAI_MEMORY_MAX_MESSAGES`     | `10`                                     | Conversation turns to keep in short-term memory (counts turns, not individual messages)                                                                                |
| `GENAI_MEMORY_SESSION_TTL_DAYS` | `0`                                      | Sessions not written to in this many days are vacuumed. `0` disables vacuum.                                                                                           |
| `GENAI_SESSION_CONCURRENCY`     | `1`                                      | Max concurrent in-flight requests per `session_id`. Raise above `1` for shared sessions used by multiple players simultaneously (e.g. team sessions).                  |
| `GENAI_SKILLS_PATH`             | `~/.local/share/amxmodx_genai/skills`    | Directory where plugin skill subdirectories are resolved                                                                                                               |

## Plugin API

```pawn
#include <amxmodx_genai>

// Per-player query - SteamID as session key, shared across all plugins by default
// callback: public MyCallback(player, const response[], bool:is_error)
// this_plugin=true isolates memory to this plugin; no_memory=true skips memory read/write
native genai_query_player(player, const prompt[], const callback[], bool:this_plugin = false, bool:no_memory = false);

// Session-scoped query - explicit key for team/group/server sessions
// callback: public MyCallback(const response[], bool:is_error)  <- no player param
// this_plugin=true prefixes session_id with this plugin's name
native genai_query(const prompt[], const callback[], const session_id[], bool:this_plugin = false, bool:no_memory = false);

// Cancel a pending query (no callback fired)
native genai_cancel(player, const session_id[] = "");

// Returns true if a query is outstanding for this player/session
native bool:genai_is_pending(player, const session_id[] = "");

// Set/append this plugin's context section in the system prompt (call in plugin_init)
native genai_set_plugin_context(const context[]);
native genai_append_plugin_context(const content[]);

// Clear short-term memory for a session (triggers long-term summarization)
native genai_clear_memory(player, const session_id[] = "");

// Register a tool the LLM can call mid-reasoning
// Tool name is auto-prefixed: "get_map" in "my_plugin.amxx" -> "my_plugin__get_map"
// callback: public MyTool(player, const args_json[], result[], maxlen)
native genai_register_tool(const name[], const description[], const callback[]);

// Declare a typed parameter for the most recently registered tool
native genai_add_tool_param(const name[], const type[], bool:required, const description[]);

// Register a skill by name (auto-prefixed, loaded from GENAI_SKILLS_PATH)
native genai_register_skill(const name[]);

// Delete long-term (summary) memory for a session without summarizing first
native genai_clear_longterm_memory(player, const session_id[] = "");
```

### Minimal example

```pawn
#include <amxmodx>
#include <amxmodx_genai>

public plugin_init()
{
    register_plugin("My Plugin", "1.0.0", "me");
    genai_set_plugin_context("You are a helpful Counter-Strike coach.");
    register_clcmd("say /ask",  "cmd_ask");
    register_clcmd("say /team", "cmd_ask_team");
}

// Per-player query
public cmd_ask(id)
{
    if (genai_is_pending(id)) {
        client_print(id, print_chat, "[AI] Still thinking...");
        return PLUGIN_HANDLED;
    }
    new args[256];
    read_args(args, sizeof(args) - 1);
    remove_quotes(args);
    genai_query_player(id, args, "on_response");
    return PLUGIN_HANDLED;
}

// Team session - all players on the same team share one conversation
public cmd_ask_team(id)
{
    new session[32];
    format(session, sizeof(session) - 1, "team_%d", get_user_team(id));
    genai_query("What is our strategy?", "on_team_response", session);
    return PLUGIN_HANDLED;
}

public on_response(id, const response[], bool:is_error)
{
    client_print(id, print_chat, "%s %s", is_error ? "[AI Error]" : "[AI]", response);
}

public on_team_response(const response[], bool:is_error)
{
    for (new i = 1; i <= get_maxplayers(); i++)
        if (is_user_connected(i))
            client_print(i, print_chat, "%s %s", is_error ? "[AI Error]" : "[Team AI]", response);
}

public client_disconnect(id)
{
    genai_cancel(id);
    genai_clear_memory(id);
}
```

### Tools with typed parameters

```pawn
public plugin_init()
{
    genai_register_tool("get_player_info", "Returns info about a player", "tool_player_info");
    genai_add_tool_param("player_id", "integer", true,  "Player index 1-32");
    genai_add_tool_param("verbose",   "boolean", false, "Include frags and deaths");
}

public tool_player_info(player, const args[], result[], maxlen)
{
    new pid = json_get_int(args, "player_id");
    // ... fill result
    return 1;
}
```

See [docs/plugin-api.md](docs/plugin-api.md) for the full API reference.

## Examples

The `examples/` directory contains ready-to-compile example plugins:

| Directory          | What it shows                                                                                             |
| ------------------ | --------------------------------------------------------------------------------------------------------- |
| `weapon_advisor/`  | `genai_register_skill`, custom tool, per-player memory                                                    |
| `admin_assistant/` | Access flags, `genai_append_plugin_context`, core tools, chat chunking                                    |
| `testable/`        | Observable side effects for integration testing; paired with `tests/integration/test_example_testable.py` |

See [`examples/README.md`](examples/README.md) for details.

## Memory

The sidecar maintains two tiers of memory per session:

- **Short-term**: raw conversation turns (last 10 turns, configurable via `GENAI_MEMORY_MAX_MESSAGES`), cleared on `genai_clear_memory`.
- **Long-term**: LLM-generated summary persisted across sessions. Automatically updated when short-term memory is cleared. Injected into the next session's system prompt so the agent remembers past interactions.

Session keys are SteamIDs by default (`genai_query_player`). Use `genai_query` with a custom key for team or server-wide sessions. Pass `no_memory=true` to either native for one-off queries that should not pollute the session.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT - see [LICENSE](LICENSE).
