# Architecture

## Overview

amxx_agent is a generic AI agent bridge for AMX Mod X game servers. It connects any AMX Mod X plugin to a configurable LLM backend through a local Python sidecar. The game server never speaks HTTPS directly; the sidecar owns that boundary.

Plugin authors wire their own tools, system prompts, skills, and session logic. The bridge itself provides no game-specific knowledge.

```mermaid
graph TD
    subgraph HLDS["CS 1.6 / HLDS"]
        core["core.amxx\nnatives + TCP queue"]
        plugin["your_plugin.amxx\nagent_query / register_tool"]
        plugin -->|calls natives| core
    end

    subgraph sidecar["amxx_agent (Python)"]
        server["server.py\nasyncio TCP listener"]
        handler["core/handler.py\nper-connection coroutine"]
        memory["core/memory.py\ntwo-tier persistent memory"]
        model["core/model.py\nmodel factory"]
        server --> handler
        handler --> memory
        handler --> model
    end

    core <-->|"newline-delimited JSON\nTCP protocol v2"| server
    model <-->|HTTPS or local| llm["LLM"]
```

## Key design decisions

**One persistent TCP socket, multiplexed across multiple queries.**
The AMX Mod X sockets API is non-blocking and poll-based. A single socket connection is opened on the first query and remains open indefinitely, multiplexing multiple concurrent queries using `request_id` fields to match requests with responses. The poll task (`task_poll_sockets`) reads all complete JSON lines per tick and dispatches them to the appropriate handler based on `request_id`. Queue slots are freed when `type=done` arrives for that request. When the queue is empty, the poll task stops and is restarted by the next `agent_query` call. See [ADR 001](adr/001-persistent-multiplexed-tcp-socket.md).

**Two-tier persistent memory.**
Short-term memory (raw conversation turns) lives in the `sessions` SQLite table and is cleared when `agent_clear_memory` is called. The number of turns kept is controlled by `AGENT_MEMORY_MAX_MESSAGES`, which counts conversation _turns_ (user+assistant pairs), not individual messages. Long-term memory lives in the `longterm` table as an LLM-generated summary. When short-term memory is cleared, the sidecar summarizes the session and merges it into long-term memory before deleting the raw turns. On the next query, the summary is injected under `## Memory from previous sessions` in the system prompt. Both tables share a single WAL-mode SQLite file (`AGENT_MEMORY_PATH`). See [ADR 002](adr/002-two-tier-persistent-memory.md).

**Tools and skills are namespaced by plugin filename.**
Both `agent_register_skill` and `agent_register_tool` prefix the registered name with the calling plugin's filename (minus `.amxx`) and a double underscore: `my_plugin__tool_name`. Two plugins can each register `"strategy"` or `"get_map"` with no collision. See [ADR 003](adr/003-plugin-naming-convention.md).

**Typed tool parameters via builder pattern.**
`agent_register_tool` is followed by `agent_add_tool_param` calls that build a JSON Schema incrementally in Pawn. The sidecar converts this to a Strands `inputSchema` so the model receives proper type constraints rather than guessing from the description. See [ADR 004](adr/004-typed-tool-parameters.md).

**Plugin-registered tools stay in AMX Mod X.**
Tools round-trip: the sidecar sends `tool_call` to the game server, the plugin callback runs synchronously, and the result comes back as `tool_result` on the same socket. Native sidecar tools (e.g. `current_datetime`) resolve without a round-trip. See [ADR 005](adr/005-plugin-tool-round-trip.md).

**Immutable base system prompt.**
The sidecar always loads `SYSTEM_PROMPT.md` as the base. Plugins can only append their own `## plugin_name` section via `agent_set_plugin_context` / `agent_append_plugin_context`. Headings inside plugin context are shifted down two levels automatically so they never conflict with the base structure.

**Swappable model backend.**
Set `AGENT_MODEL_BACKEND` to switch LLM providers without code changes. Supported values: `ollama` (default, local), `anthropic`, `bedrock` (AWS), `litellm` (proxy - covers OpenRouter, Groq, Cohere, etc.), `openai` (OpenAI-compatible API).

**Session memory TTL and concurrency.**
`AGENT_MEMORY_SESSION_TTL_DAYS` (default `0`, disabled) enables a background vacuum that removes sessions inactive for the specified number of days, preventing unbounded SQLite growth on long-running servers. `AGENT_SESSION_CONCURRENCY` (default `1`) controls how many in-flight requests are allowed per `session_id` simultaneously; raise it above `1` for shared sessions where multiple players query the same conversation at once (e.g. team sessions).

## Component map

| File                                                        | Responsibility                                                                                 |
| ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `plugins/amxx_agent/core.sma`                               | AMX Mod X plugin: native registration, socket queue, poll loop, message dispatch               |
| `plugins/amxx_agent/include/constants.inc`                  | Shared `#define` limits                                                                        |
| `plugins/amxx_agent/include/json.inc`                       | Minimal flat-JSON parser                                                                       |
| `plugins/amxx_agent/include/queue.inc`                      | Queue and tool/skill registry globals, slot helpers                                            |
| `plugins/amxx_agent/include/core_tools.inc`                 | Built-in tool definitions (registered by core.sma)                                             |
| `plugins/amxx_agent/include/core_skills.inc`                | Built-in skill registration (amxmodx-reference)                                                |
| `plugins/include/amxx_agent.inc`                            | Public native declarations for third-party plugins                                             |
| `examples/weapon_advisor/`                                  | Example: `agent_register_skill` + custom tool + per-player memory                              |
| `examples/admin_assistant/`                                 | Example: tools, skill, cancel, clear_longterm_memory, access control                           |
| `examples/testable/`                                        | Example: all plugin API natives exercised; observable for integration testing                  |
| `examples/testable/skills/ai_testable__testable-knowledge/` | Skill shipped alongside `testable`; deploy to `AGENT_SKILLS_PATH`                              |
| `src/amxx_agent/server.py`                                  | `asyncio.start_server` entry point; `_handle_persistent` multiplexes requests                  |
| `src/amxx_agent/config.py`                                  | Pydantic settings loaded from `AGENT_*` env vars                                               |
| `src/amxx_agent/logger.py`                                  | Root logger configuration (level, format); call `setup()` once at startup                      |
| `src/amxx_agent/core/handler.py`                            | Per-connection logic: reads query, runs agent, manages memory, sends frames                    |
| `src/amxx_agent/core/protocol.py`                           | JSON framing helpers                                                                           |
| `src/amxx_agent/core/memory.py`                             | SQLite-backed two-tier memory: short-term turns + long-term summaries; vacuum task             |
| `src/amxx_agent/core/model.py`                              | Model factory: multi-backend LLM provider (Bedrock, Ollama, LiteLLM, OpenAI-compatible)        |
| `src/amxx_agent/core/messages.py`                           | Message type definitions for the wire protocol                                                 |
| `src/amxx_agent/core/summarize.py`                          | LLM-based session summarization for long-term memory                                           |
| `src/amxx_agent/tools/plugin.py`                            | Dynamic tool factory for AMX Mod X-registered tools (typed JSON schema, ID-matched round-trip) |
| `src/amxx_agent/tools/native.py`                            | Built-in sidecar tools (e.g. `current_datetime`) resolved without a game server round-trip     |
| `src/amxx_agent/skills/loader.py`                           | Loads `AgentSkills` from disk for plugin-registered and built-in skills                        |
| `src/amxx_agent/SYSTEM_PROMPT.md`                           | Immutable base agent persona                                                                   |
