# ADR 005: Plugin-registered tools round-trip through AMX Mod X

## Status

Accepted

## Context

When the agent decides to call a plugin-registered tool (e.g. `my_plugin__get_score`), the tool logic lives in the AMX Mod X plugin, not in the Python sidecar. The sidecar must invoke that logic and return the result to the agent before continuing the reasoning loop. Re-implementing plugin tool logic as Python shims in the sidecar is not viable - the point is that plugin authors write tools in Pawn with direct access to live game state. AMX Mod X has no HTTP server, so the sidecar cannot make an outbound callback.

## Decision

Plugin tool calls round-trip over the same persistent TCP connection (see ADR 001):

1. Sidecar receives a `tool_use` block from the LLM.
2. Sidecar sends `{"type": "tool_call", "request_id": "...", "id": "toolu_...", "name": "...", "args": "..."}` to AMX Mod X.
3. AMX Mod X dispatches to the registered callback synchronously within the same game tick.
4. AMX Mod X sends `{"type": "tool_result", "request_id": "...", "id": "toolu_...", "content": "..."}` back.
5. Sidecar feeds the result to the agent and continues the reasoning loop.

Built-in sidecar tools (e.g. `current_datetime`) resolve without a round-trip - they run directly in the sidecar.

## Alternatives Considered

- **Python shims in the sidecar** - the sidecar re-implements tool logic in Python; breaks the whole premise that plugin authors write tools in Pawn with direct access to live game state.
- **Sidecar opens a reverse connection to AMX Mod X** - requires AMX Mod X to listen on a second port, adding complexity and a second connection lifecycle to manage.
- **Pre-registered result cache (plugin pushes data before query)** - plugin pushes live state into the sidecar before each query so tools resolve locally; requires predicting which data the agent will need and keeping it fresh, which is not viable for dynamic tool calls.
- **gRPC / MessagePack** - lower overhead and stronger typing, but adds external dependencies and build complexity for both the Python sidecar and the Pawn plugin.

## Consequences

- Plugin tools have full access to live game state (player positions, scores, cvars, etc.).
- Tool calls add one network round-trip to the agent loop. Acceptable for local TCP.
- The AMX Mod X callback runs in the game tick, blocking the server for its duration. Tool callbacks should be fast.
- The `id` field from `tool_call` must be echoed in `tool_result` so the sidecar can correlate them for the LLM message history.
