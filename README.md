# AMX Mod X GenAI

[![CI](https://img.shields.io/github/actions/workflow/status/omar-hindawi98/amxmodx-genai/ci.yml?branch=main&label=CI)](https://github.com/omar-hindawi98/amxmodx-genai/actions/workflows/ci.yml)
[![E2E](https://img.shields.io/github/actions/workflow/status/omar-hindawi98/amxmodx-genai/e2e.yml?branch=main&label=E2E)](https://github.com/omar-hindawi98/amxmodx-genai/actions/workflows/e2e.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

LLM agent bridge for AMXMODX game servers. Plugins call simple Pawn natives; a local Python TCP sidecar runs a Strands agent loop against the Anthropic API (or a local Ollama model) with two-tier persistent memory, plugin-registered tools and skills, and a composable system prompt.

```
CS 1.6 server
  amxmodx
    core.amxx  <----TCP (protocol v2)---->  amxmodx_genai sidecar  --HTTPS-->  Anthropic API
    your_plugin.amxx
```

## Requirements

- AMXMODX 1.8.2+
- [AMXMODX Sockets](https://www.amxmodx.org/sc/sockets.php) module
- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- `ANTHROPIC_API_KEY` environment variable (or Ollama for local inference)

## Installation

### Sidecar

```sh
uv sync
ANTHROPIC_API_KEY=sk-ant-... uv run genai-sidecar
```

Use Ollama instead of the Anthropic API:

```sh
GENAI_BACKEND=ollama GENAI_OLLAMA_MODEL=llama3.2 uv run genai-sidecar
```

### AMXMODX plugin

1. Compile `plugins/amxmodx_genai/core.sma` and copy `core.amxx` to `addons/amxmodx/plugins/`.
2. Copy `plugins/include/amxmodx_genai.inc` to `addons/amxmodx/scripting/include/`.
3. Add `core.amxx` before your plugin in `addons/amxmodx/configs/plugins.ini`.

## Configuration

### CVars (game server)

| CVar | Default | Description |
|------|---------|-------------|
| `genai_host` | `127.0.0.1` | Sidecar host |
| `genai_port` | `27016` | Sidecar port |

### Environment variables (sidecar)

| Variable | Default | Description |
|----------|---------|-------------|
| `GENAI_HOST` | `127.0.0.1` | Bind address |
| `GENAI_PORT` | `27016` | Bind port |
| `GENAI_BACKEND` | `anthropic` | `anthropic` or `ollama` |
| `GENAI_MODEL` | `claude-haiku-4-5-20251001` | Anthropic model ID |
| `GENAI_TOKENS` | `512` | `max_tokens` per response |
| `GENAI_OLLAMA_HOST` | `http://localhost:11434` | Ollama base URL |
| `GENAI_OLLAMA_MODEL` | `llama3.2` | Ollama model name |
| `GENAI_MEMORY_PATH` | `~/.local/share/amxmodx_genai/memory.db` | SQLite memory file |
| `GENAI_SKILLS_PATH` | `./skills` | Directory containing skill subdirectories |

## Plugin API

```pawn
#include <amxmodx_genai>

// Send a prompt; response delivered to callback(player, response[])
native genai_query(player, const prompt[], const callback[], const session_id[] = "");

// Cancel a pending query (no callback fired)
native genai_cancel(player, const session_id[] = "");

// Returns true if a query is outstanding for this player/session
native bool:genai_is_pending(player, const session_id[] = "");

// Set/append this plugin's context section in the system prompt (call in plugin_init)
native genai_set_plugin_context(const context[]);
native genai_append_plugin_context(const content[]);

// Clear short-term memory for a session (triggers long-term summarization)
native genai_clear_memory(player, const session_id[] = "");

// Register a tool Claude can call mid-reasoning
// Tool name is auto-prefixed: "get_map" in "my_plugin.amxx" -> "my_plugin__get_map"
// callback: public MyTool(player, const args_json[], result[], maxlen)
native genai_register_tool(const name[], const description[], const callback[]);

// Declare a typed parameter for the most recently registered tool
native genai_add_tool_param(const name[], const type[], bool:required, const description[]);

// Register a skill by name (auto-prefixed, loaded from GENAI_SKILLS_PATH)
native genai_register_skill(const name[]);
```

### Minimal example

```pawn
#include <amxmodx>
#include <amxmodx_genai>

public plugin_init()
{
    register_plugin("My Plugin", "1.0.0", "me");
    genai_set_plugin_context("You are a helpful Counter-Strike coach.");
    register_clcmd("say /ask", "cmd_ask");
}

public cmd_ask(id)
{
    if (genai_is_pending(id))
    {
        client_print(id, print_chat, "[AI] Still thinking...");
        return PLUGIN_HANDLED;
    }
    new args[256];
    read_args(args, sizeof(args) - 1);
    remove_quotes(args);
    genai_query(id, args, "on_response");
    return PLUGIN_HANDLED;
}

public on_response(id, const response[])
{
    client_print(id, print_chat, "[AI] %s", response);
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

## Memory

The sidecar maintains two tiers of memory per session:

- **Short-term**: raw conversation turns (last 20 messages), cleared on `genai_clear_memory`.
- **Long-term**: LLM-generated summary persisted across sessions. Automatically updated when short-term memory is cleared. Injected into the next session's system prompt so the agent remembers past interactions.

Session IDs are arbitrary strings controlled by the plugin. Use a player's auth ID (Steam ID) as the session key to get stable cross-session memory for the same player.

## Development

```sh
uv sync --dev
uv run ruff check .
uv run ruff format --check .
uv run pytest                        # unit + e2e (mocked agent, no API key needed)
uv run pytest -m live                # live tests (requires sidecar running)
```

### Docker

Run the full AMX e2e suite (compiles plugins, starts game server + sidecar):

```sh
docker compose up
```

Run live loop tests against Ollama:

```sh
docker compose --profile live up --abort-on-container-exit live_test
```

## License

MIT - see [LICENSE](LICENSE).
