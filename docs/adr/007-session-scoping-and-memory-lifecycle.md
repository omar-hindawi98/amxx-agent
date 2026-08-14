# ADR 007: Session scoping and memory lifecycle

## Status

Accepted

## Context

Memory is keyed on `session_id`. The right scope for that key depends entirely on what a plugin is trying to do. A general assistant plugin wants per-player memory shared across all plugins. A team-tactics plugin wants memory shared across all players on a team. A one-off stat-lookup plugin does not want memory at all. Without a clear model, plugin authors either share memory they should not, isolate memory they should share, or accumulate stale sessions indefinitely.

Separately, a game server that runs continuously accumulates a session row for every player who has ever connected. Without a cleanup mechanism this grows without bound.

## Decision

### Session scoping

The sidecar is scoping-agnostic: it keys all memory on whatever `session_id` string the plugin sends. The Pawn API provides two natives so plugin authors express intent rather than string conventions:

- `genai_query_player(player, prompt, callback, this_plugin=false, no_memory=false)` - per-player scope. The session key is the player's SteamID (stable across reconnects and map changes). When `this_plugin=false` (default) all plugins share memory for a player. When `this_plugin=true` memory is isolated to this plugin. Callback fires with the given player index.
- `genai_query(prompt, callback, session_id, this_plugin=false, no_memory=false)` - explicit session key for group/global/custom scopes. No player parameter; callback signature is `(const response[])`. When `this_plugin=true`, session_id is prefixed with the plugin name.

Supported patterns:

| Scope | Native to use | Notes |
|---|---|---|
| One player, all plugins (default) | `genai_query_player(player, ...)` | SteamID as key; shared across all plugins |
| One player, this plugin only | `genai_query_player(player, ..., true)` | Key is `"{plugin}__{steamid}"` |
| Team / group | `genai_query(..., "team_2")` | All callers with the same key share context; callback is `(response[])` |
| Server-wide | `genai_query(..., "server")` | Single session for all plugins; callback is `(response[])` |

The sidecar falls back to `"server"` when it receives an empty `session_id` (server console context where no SteamID is available).

### Ephemeral queries (`no_memory`)

Both `genai_query_player` and `genai_query` accept a `no_memory` boolean (default `false`). When `true`:
- Short-term and long-term memory are not read - the agent starts with no history.
- The response is not written back to memory - no turn is stored.
- The `session_meta.last_seen` timestamp is not updated.

Use this for one-off lookups (stat queries, admin commands) that should not pollute a session's conversation history.

### Session TTL and vacuum

`GENAI_MEMORY_SESSION_TTL_DAYS` (default `0`, disabled) sets how many days of inactivity before a session is considered stale. When nonzero, a background task wakes every hour and deletes all data (`sessions`, `longterm`, `session_meta` rows) for sessions whose `last_seen` timestamp is older than the TTL.

`last_seen` is updated on every `memory.update()` call (i.e. every non-ephemeral query that produces a response). Sessions that exist only as long-term summaries (where `clear_memory` was called but no subsequent query was made) retain their `last_seen` from the last query before the clear.

### Group session concurrency

The per-session semaphore that prevents one session from starving others (see ADR 001) defaults to `1` - one in-flight request per session at a time. For group sessions where many players query simultaneously (e.g. a team session), `GENAI_SESSION_CONCURRENCY` raises this limit. The value applies to all sessions on the sidecar.

## Alternatives Considered

### Session scoping

- **Raw `session_id` string only** - one flexible native; plugin authors build the key themselves. Rejected: requires knowing the string conventions (SteamID format, plugin prefix pattern) to get the right scope, which is not obvious from the API.
- **Automatic namespacing by plugin** - the sidecar could prefix `session_id` with the plugin name automatically, enforcing per-plugin isolation by default. Rejected: the primary use case is sharing memory across plugins for the same player; forcing isolation by default breaks that.
- **Three separate natives** - `genai_query_player`, `genai_query_plugin`, `genai_query`. Rejected in favor of two: the plugin-only scope is just `genai_query_player` with `this_plugin=true`, which reads naturally and keeps the API surface small.

### Ephemeral queries

- **Throwaway session_id (UUID per query)** - plugin generates a random `session_id` to get no history; works today but writes a row to `session_meta` and leaves orphan rows that require cleanup.
- **`max_history: int` field** - limit history length per query rather than a binary flag; more flexible but adds complexity for a common case that is simply "no memory at all."

### Session TTL

- **No cleanup (current default)** - acceptable for small servers or short-lived deployments; problematic on public servers running for months.
- **Manual vacuum via admin command** - requires operator intervention; easy to forget.
- **Row-level TTL via SQLite trigger** - SQLite does not support TTL triggers natively; would require a scheduled task anyway.
- **Cleanup on disconnect event** - AMX Mod X could send a `forget_player` message on disconnect; fast but loses memory immediately on accidental disconnect rather than on true inactivity.

### Group session concurrency

- **Per-session configurable limit passed in the query** - maximum flexibility but requires the plugin to know and pass the right value on every query; error-prone.
- **Detect group sessions automatically** - no reliable way to infer from the `session_id` string whether a session is shared.
- **Remove per-session semaphore for group sessions** - allowing unbounded concurrency on a shared session creates write races on the memory table and unpredictable conversation ordering.

## Consequences

- Plugin authors have a clear, documented model for choosing `session_id`.
- Ephemeral queries incur no memory I/O overhead and no storage cost.
- Servers with `GENAI_MEMORY_SESSION_TTL_DAYS` set automatically reclaim storage without operator intervention.
- Group sessions with elevated `GENAI_SESSION_CONCURRENCY` may produce out-of-order memory writes if multiple players respond faster than the semaphore serializes them; this is an accepted tradeoff for group contexts where strict ordering matters less.
- `session_meta.last_seen` is only updated on writes, not reads. A session queried read-only (via `no_memory=True` exclusively) never advances its TTL clock and will be vacuumed after `ttl_days` of inactivity even if it still has a long-term summary.
