# ADR 001: Persistent multiplexed TCP socket

## Status

Accepted

## Context

AMX Mod X plugins communicate with the Python sidecar over a local TCP connection. The AMX Mod X sockets API is non-blocking and poll-based; a plugin cannot block waiting for a response. Multiple players can submit queries simultaneously.

Opening one connection per query would require managing concurrent non-blocking handshakes and adds per-query overhead. A single persistent connection limited to one query at a time would serialise all queries, increasing per-player latency under load.

## Decision

Use a single persistent TCP connection that multiplexes all queries using a `request_id` field. The connection is opened on the first `genai_query` call and held open until the plugin shuts down or an error occurs. The AMX Mod X poll task reads all complete JSON lines per tick and dispatches each frame to the correct handler by `request_id`. The queue slot is freed when a `type=done` frame arrives for that `request_id`.

## Consequences

- Queue slots (up to `MAX_QUEUE = 32`) limit concurrency, not connections. Simpler resource management.
- All message types (`query`, `tool_call`, `tool_result`, `response`, `done`, `clear_memory`) carry `request_id` for consistent multiplexing.
- A single connection failure affects all in-flight queries. The plugin drops them and re-opens on the next call.
- The poll task is only active while queries are in flight; it stops when the queue empties and restarts on the next `genai_query`.
