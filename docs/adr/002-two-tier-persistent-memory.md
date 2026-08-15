# ADR 002: Two-tier persistent memory

## Status

Accepted

## Context

An AI agent bridge for a game server needs memory that survives sidecar restarts, does not grow unboundedly (game servers run indefinitely; raw turns accumulate), and can be cleared mid-session without losing all context (e.g. a new map starts).

In-memory storage is lost on restart. Storing raw turns in SQLite without a limit grows forever and increases LLM latency and cost with context length. A fixed rolling window bounds size but cold-starts every session with no cross-session recall.

## Decision

Maintain two SQLite tables in a single WAL-mode database (`AGENT_MEMORY_PATH`):

- `sessions` - raw conversation turns, capped at `AGENT_MEMORY_MAX_MESSAGES` turns (user+assistant pairs).
- `longterm` - one LLM-generated summary row per `session_id`, merged on each `clear_memory` call.

On `agent_clear_memory`: summarize the current short-term turns, merge the summary into `longterm`, then delete the turns. On the next query, inject the summary under `## Memory from previous sessions` in the system prompt.

Session IDs default to the player's SteamID. Bots and LAN clients without a SteamID fall back to `str(player)`. Plugins can pass a custom `session_id` to share memory across players or create player-independent sessions.

## Alternatives Considered

- **In-memory only** - simplest, zero overhead, but all context is lost on sidecar restart or server reboot.
- **Raw turns only, no summarization** - persistent but grows unboundedly; long sessions push context length and cost past acceptable limits.
- **Per-turn summarization** - compress every turn as it arrives; loses conversational detail that is useful within a session and adds LLM cost on every message.
- **Vector store (semantic search)** - richer recall but adds an external dependency, significant operational complexity, and embedding cost for a game-server deployment.
- **External store (Redis, Postgres)** - unnecessary operational burden for a self-contained sidecar; SQLite WAL mode handles the concurrency requirements.

## Consequences

- Context window stays bounded regardless of session length.
- Cross-session memory survives sidecar restarts.
- Summarization costs one extra LLM call per `clear_memory`. Acceptable because `clear_memory` is called infrequently (typically on player disconnect).
- Long-term memory is never cleared by `clear_memory`; it accumulates across sessions. A separate `clear_longterm` message wipes it when needed (e.g. player account reset).
- `AGENT_MEMORY_MAX_MESSAGES` counts turns (user+assistant pairs), not individual messages. Default `10` turns = up to 20 DB rows.
