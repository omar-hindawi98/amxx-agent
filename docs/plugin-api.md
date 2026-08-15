# Plugin API

This guide covers writing an AMX Mod X plugin that uses amxx_agent.

## Setup

Copy `plugins/include/amxx_agent.inc` to your server's `addons/amxmodx/scripting/include/` directory and add `#include <amxx_agent>` to your plugin.

`core.amxx` must be loaded before your plugin in `plugins.ini`.

## Natives

### agent_query_player

```pawn
native agent_query_player(player, const prompt[], const callback[], bool:this_plugin = false, bool:no_memory = false);
```

Sends a prompt scoped to this player's memory. The session key is the player's SteamID so memory survives reconnects and map changes.

```pawn
// callback signature
public on_response(player, const response[], bool:is_error)
```

`is_error` is `true` when the response is a sidecar error (timeout, unauthorized, AI unavailable) rather than a real AI reply.

| Parameter     | Description                                                                                                                                                                         |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `player`      | Client index                                                                                                                                                                        |
| `prompt`      | User message to send                                                                                                                                                                |
| `callback`    | Name of public function in calling plugin to receive response                                                                                                                       |
| `this_plugin` | When `false` (default), memory is shared across all plugins for the same player. When `true`, memory is isolated to this plugin only (session key becomes `"{plugin}__{steamid}"`). |
| `no_memory`   | When `true`, the query runs with no history and the response is not stored. Use for one-off lookups that should not pollute the session.                                            |

Returns the queue slot index on success, or `-1` if the queue is full or the socket failed to open.

---

### agent_query

```pawn
native agent_query(const prompt[], const callback[], const session_id[], bool:this_plugin = false, bool:no_memory = false);
```

Sends a prompt with an explicit session key. Use for team/group sessions, server-wide sessions, or any custom shared context. All callers that pass the same `session_id` share the same memory.

```pawn
// callback signature - no player parameter
public on_team_response(const response[], bool:is_error)
```

`is_error` is `true` when the response is a sidecar error rather than a real AI reply.

| Parameter     | Description                                                                                                              |
| ------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `prompt`      | User message to send                                                                                                     |
| `callback`    | Name of public function in calling plugin to receive response                                                            |
| `session_id`  | Conversation history key. All callers passing the same value share memory.                                               |
| `this_plugin` | When `true`, prefixes `session_id` with this plugin's name so two plugins using `"team_ct"` don't share the same memory. |
| `no_memory`   | When `true`, the query runs with no history and the response is not stored.                                              |

Returns the queue slot index on success, or `-1` if the queue is full or the socket failed to open.

**Session scope examples:**

```pawn
// Team session - all CTs share one conversation
new session[32];
format(session, sizeof(session) - 1, "team_%d", get_user_team(id));
agent_query("What is our team strategy?", "on_team_response", session);

// Server-wide session
agent_query("Summarize the last round.", "on_summary", "server");
```

---

### agent_cancel

```pawn
native agent_cancel(player, const session_id[] = "");
```

Cancels any pending query for this player or session. No callback is fired.

---

### agent_is_pending

```pawn
native bool:agent_is_pending(player, const session_id[] = "");
```

Returns `true` if a query is currently in-flight for this player or session. The `session_id` defaults to the player's SteamID when empty.

---

### agent_set_plugin_context

```pawn
native agent_set_plugin_context(const context[]);
```

Sets this plugin's context section. The text is appended to the immutable base system prompt under a `## <plugin_name>` heading - it cannot override the base. Replaces any previously set plugin context. Call in `plugin_init`.

---

### agent_append_plugin_context

```pawn
native agent_append_plugin_context(const content[]);
```

Appends text to this plugin's context section. A newline is inserted between the existing content and the new text. Headings inside the content are shifted down two levels (`#` becomes `###`, `##` becomes `####`) so they nest correctly under the plugin's `##` section heading.

```pawn
public plugin_init()
{
    agent_set_plugin_context("You are a helpful assistant for this game server.");
    agent_append_plugin_context("Always respond in one or two sentences.");
    agent_append_plugin_context("Current map: de_dust2. Round budget: $3000.");
}
```

---

### agent_clear_memory

```pawn
native agent_clear_memory(player, const session_id[] = "");
```

Clears short-term memory (conversation turns) for a session. Call on player disconnect or when starting a new context. The `session_id` defaults to the player's SteamID when empty.

Before deleting the turns, the sidecar summarizes the session and merges the summary into long-term memory. The next query for that session will have the summary injected into its system prompt. Long-term memory is never cleared by this call.

Memory is SQLite-backed and survives sidecar restarts.

---

### agent_register_tool

```pawn
native agent_register_tool(const name[], const description[], const callback[]);
```

Registers a tool the agent can call mid-reasoning. The agent sees `name` and `description` when deciding whether to use it. The callback is invoked synchronously when the agent requests the tool.

The tool name is automatically prefixed with the plugin filename (minus `.amxx`) using a double underscore separator. A tool named `"get_map"` in `my_coach.amxx` is exposed to the agent as `"my_coach__get_map"`. This prevents name collisions across plugins.

```pawn
// callback signature
public my_tool(player, const args_json[], result[], maxlen)
```

- `args_json` - JSON object of arguments the agent passed. Parse with `json_get_string` / `json_get_int` from `json.inc`.
- `result` - write the tool result string here.
- `maxlen` - size of the result buffer.
- Return `1` on success.

Follow `agent_register_tool` immediately with `agent_add_tool_param` calls to declare expected arguments. Without parameter declarations the agent must guess the argument format from the description alone.

---

### agent_add_tool_param

```pawn
native agent_add_tool_param(const name[], const type[], bool:required, const description[]);
```

Adds a typed parameter to the most recently registered tool. Call immediately after `agent_register_tool`, once per parameter.

| Argument      | Description                                                    |
| ------------- | -------------------------------------------------------------- |
| `name`        | Parameter name in `snake_case`                                 |
| `type`        | JSON type: `"string"`, `"integer"`, `"boolean"`, or `"number"` |
| `required`    | `true` if the agent must always supply this argument           |
| `description` | One sentence telling the agent what this argument represents   |

```pawn
agent_register_tool("get_player_info", "Returns info about a player", "tool_player_info");
agent_add_tool_param("player_id",     "integer", true,  "Player index (1-32)");
agent_add_tool_param("include_stats", "boolean", false, "Include frags, deaths, and assists");
```

---

### agent_clear_longterm_memory

```pawn
native agent_clear_longterm_memory(player, const session_id[] = "");
```

Deletes the long-term (summary) memory for a session without touching short-term memory. Unlike `agent_clear_memory`, no summarization is performed - the persistent summary is discarded entirely. Use for a full memory reset, e.g. at the start of a new season when past context is no longer relevant.

---

### agent_register_skill

```pawn
native agent_register_skill(const name[]);
```

Registers a skill directory the agent can use for all queries from the calling plugin. Call in `plugin_init`.

The skill name is automatically prefixed with the plugin filename (minus `.amxx`) using a double underscore separator. A skill named `"strategy"` in `my_coach.amxx` is registered as `"my_coach__strategy"`. This prevents collisions between plugins.

The sidecar resolves skills by looking for `<name>/SKILL.md` under `AGENT_SKILLS_PATH` (defaults to `~/.local/share/amxx_agent/skills`, overridden with the `AGENT_SKILLS_PATH` env var). Deploy the skill directory to that location on the sidecar machine.

**Skill directory structure** (`skills/my_coach__strategy/`):

```
my_coach__strategy/
  SKILL.md            <- required
  references/         <- optional: markdown docs the agent can read
  assets/             <- optional: static data files
```

**SKILL.md format:**

```markdown
---
name: my_coach__strategy
description: Provides tactical strategy advice for the current map.
---

When asked about strategy, analyze the current situation and suggest a plan.
```

The `name` field in the SKILL.md frontmatter must match the directory name exactly.

```pawn
public plugin_init()
{
    agent_register_skill("strategy");   // -> my_coach__strategy
    agent_register_skill("economy");    // -> my_coach__economy
}
```

**Built-in skills:**

The core plugin optionally registers a built-in `amxmodx-reference` skill (controlled by `agent_core_skills` CVar, default `1`). This skill provides the agent with reference knowledge about AMX Mod X, Pawn scripting, server administration, and common gameplay systems. Plugins can also register their own skills or build on the reference skill.

The `amxmodx-reference` skill is located at `plugins/amxx_agent/include/skills/amxmodx-reference/SKILL.md` in the plugin package. To use it, ensure `AGENT_SKILLS_PATH` (environment variable on the sidecar) points to the directory containing `amxmodx-reference/` (i.e., the `include/skills/` directory from the plugin package).

---

## Example plugin

```pawn
#include <amxmodx>
#include <amxx_agent>

public plugin_init()
{
    register_plugin("My Plugin", "1.0.0", "me");

    agent_set_plugin_context("You are a helpful assistant for this game server.");
    agent_append_plugin_context("Keep answers brief: one or two sentences.");

    agent_register_tool("get_map", "Returns the current map name", "tool_get_map");
    agent_register_skill("tactics");

    register_clcmd("say /ask",  "cmd_ask");
    register_clcmd("say /team", "cmd_ask_team");
}

// Per-player query - memory shared across all plugins
public cmd_ask(id)
{
    if (agent_is_pending(id)) {
        client_print(id, print_chat, "[AI] Still thinking...");
        return PLUGIN_HANDLED;
    }

    new args[256];
    read_args(args, sizeof(args) - 1);
    remove_quotes(args);

    if (!args[0]) {
        client_print(id, print_chat, "[AI] Usage: /ask <question>");
        return PLUGIN_HANDLED;
    }

    agent_query_player(id, args, "on_response");
    return PLUGIN_HANDLED;
}

// Team session - all players on the same team share one conversation
public cmd_ask_team(id)
{
    new session[32];
    format(session, sizeof(session) - 1, "team_%d", get_user_team(id));
    agent_query("What is our team strategy?", "on_team_response", session);
    return PLUGIN_HANDLED;
}

public on_response(id, const response[], bool:is_error)
{
    if (is_error) {
        client_print(id, print_chat, "[AI] Error: %s", response);
        return;
    }
    client_print(id, print_chat, "[AI] %s", response);
}

public on_team_response(const response[], bool:is_error)
{
    for (new i = 1; i <= get_maxplayers(); i++)
        if (is_user_connected(i))
            client_print(i, print_chat, "%s %s", is_error ? "[AI Error]" : "[Team AI]", response);
}

public tool_get_map(player, const args[], result[], maxlen)
{
    get_mapname(result, maxlen);
    return 1;
}

public client_disconnect(id)
{
    agent_cancel(id);
    agent_clear_memory(id);  // triggers long-term summarization
}
```

## Tool argument parsing

When the agent calls a tool, `args_json` is a flat JSON object. Use the helpers from `json.inc` (in `amxx_agent/include/`):

```pawn
#include <json>

public tool_example(player, const args[], result[], maxlen)
{
    new item[64];
    new count = json_get_int(args, "count");
    json_get_string(args, "item", item, sizeof(item) - 1);

    format(result, maxlen - 1, "item=%s count=%d", item, count);
    return 1;
}
```

`json_get_string` returns `1` on success, `0` if the key is absent. `json_get_int` returns `0` for missing keys.

## System prompt composition

The sidecar always uses its base `SYSTEM_PROMPT.md` - this cannot be overridden. The full system prompt assembled per query is:

```
# AMX MOD X GenAI Agent      <- base (immutable)
## Environment
...

## Memory from previous sessions   <- long-term summary (when present)
- Player prefers AK47
- Usually saves on pistol rounds

## my_plugin                       <- plugin context (when set)
<your plugin context here>
```

Build domain knowledge into `agent_set_plugin_context` / `agent_append_plugin_context`. Headings inside your context text start at `###` automatically.

## Limits

| Constant         | Default | Description                               |
| ---------------- | ------- | ----------------------------------------- |
| `MAX_QUEUE`      | 32      | Concurrent in-flight queries              |
| `MAX_TOOLS`      | 32      | Registered tools across all plugins       |
| `MAX_SKILLS`     | 32      | Registered skills across all plugins      |
| `MAX_SESSION_ID` | 64      | Session ID string length                  |
| `MAX_PROMPT`     | 8192    | Prompt string length                      |
| `MAX_RESPONSE`   | 4096    | Response / tool result buffer             |
| `MAX_SYSTEM`     | 8192    | System prompt context length (per plugin) |

These are defined in `plugins/amxx_agent/include/constants.inc`.
