# ADR 002: Two-tier persistent memory

## Status

Accepted

## Context

An AI agent bridge for a game server needs memory that survives sidecar restarts, does not grow unboundedly (game servers run indefinitely; raw turns accumulate), and can be cleared mid-session without losing all context (e.g. a new map starts).

In-memory storage is lost on restart. Storing raw turns in SQLite without a limit grows forever and increases LLM latency and cost with context length. A fixed rolling window bounds size but cold-starts every session with no cross-session recall.

## Decision

Maintain two SQLite tables in a single WAL-mode database (`GENAI_MEMORY_PATH`):

- `sessions` - raw conversation turns, capped at `GENAI_MEMORY_MAX_MESSAGES` turns (user+assistant pairs).
- `longterm` - one LLM-generated summary row per `session_id`, merged on each `clear_memory` call.

On `genai_clear_memory`: summarize the current short-term turns, merge the summary into `longterm`, then delete the turns. On the next query, inject the summary under `## Memory from previous sessions` in the system prompt.

Session IDs default to the player's SteamID. Bots and LAN clients without a SteamID fall back to `str(player)`. Plugins can pass a custom `session_id` to share memory across players or create player-independent sessions.

## Consequences

- Context window stays bounded regardless of session length.
- Cross-session memory survives sidecar restarts.
- Summarization costs one extra LLM call per `clear_memory`. Acceptable because `clear_memory` is called infrequently (typically on player disconnect).
- Long-term memory is never cleared by `clear_memory`; it accumulates across sessions. There is currently no API to wipe long-term memory.
- `GENAI_MEMORY_MAX_MESSAGES` counts turns (user+assistant pairs), not individual messages. `20` turns = up to 40 DB rows.
