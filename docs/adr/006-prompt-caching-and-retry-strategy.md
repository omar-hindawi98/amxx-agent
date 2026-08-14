# ADR 006: Prompt caching and retry strategy

## Status

Accepted

## Context

Each query rebuilds the full system prompt (base instructions + plugin context + long-term memory) and re-sends the entire conversation history to the model. For an Anthropic-backed deployment, the static portions of the system prompt and accumulated history are re-billed as input tokens on every request, making active sessions increasingly expensive.

Separately, transient LLM API failures (rate limits, service unavailable) need a retry mechanism. The original approach retried the entire agent invocation at the Python level, which re-sends the full context and all tool definitions on each attempt. It also retried unrecoverable failures (`MaxTokensReachedException`, `ContextWindowOverflowException`) where a retry can never succeed.

## Decision

### Prompt caching

`_build_system_prompt` returns `list[SystemContentBlock]` instead of a plain string. The list is split at a cache point:

1. Static block: base system prompt + plugin context (same across all requests from a given plugin).
2. `cachePoint` marker: tells Anthropic to cache everything before this point.
3. Dynamic block (optional): long-term memory summary (changes after each `clear_memory`).

The Strands `Agent` accepts `str | list[SystemContentBlock]` for `system_prompt`. Backends that do not support `cachePoint` (Ollama, OpenAI, LiteLLM) receive the list and ignore the cache-point entry.

### Retry strategy

Retry logic is implemented as a Strands `HookProvider` (`_RetryHook`) registered on the agent via `hooks=[_RetryHook()]`. On `AfterModelCallEvent`, if `event.exception` is set and is not an unrecoverable type, the hook sets `event.retry = True` and sleeps with exponential backoff (`2^n` seconds, max `_MAX_HOOK_RETRIES = 1` retry).

`MaxTokensReachedException` and `ContextWindowOverflowException` are caught at the outer handler level and return specific user-facing messages without retrying:
- Max tokens: `"(response too long)"`
- Context overflow: `"(conversation too long, try clearing memory)"`

## Alternatives Considered

### Prompt caching

- **No caching, plain string system prompt** - simplest; full input tokens billed on every request regardless of how static the content is.
- **`CacheConfig(strategy="auto")` on the model** - supported only by `BedrockModel`, not `AnthropicModel`; not portable across backends.
- **Cache the entire system prompt as one block** - long-term memory is dynamic; including it before the cache point would invalidate the cache on every `clear_memory` call, defeating the purpose.
- **Separate static and dynamic system prompts as distinct API fields** - the Anthropic API has a single system field; splitting requires a non-standard extension.

### Retry strategy

- **Manual retry loop at agent-invocation level** - the previous approach; retries re-send the full context and tool definitions on each attempt, wasting tokens and adding latency for all failure types including unrecoverable ones.
- **No retry** - transient rate-limit errors surface as `(AI unavailable)` to the player, which is a poor experience for failures that resolve in seconds.
- **Fixed sleep (1s)** - does not back off under sustained throttling; a burst of 32 concurrent requests all retrying at the same interval amplifies the rate-limit problem.
- **Retry at the outer handler level with `MaxTokensReachedException` excluded** - still re-sends full context; model-call-level hooks retry only the failing API call, not the whole agent loop.

## Consequences

- Static system prompt content (base + plugin context) is cached after the first request from a given plugin. Subsequent requests pay ~10% of normal input token cost for the cached portion.
- Long-term memory is never part of the cached block, so memory updates do not invalidate the cache.
- Unrecoverable failures fail fast with a specific message; no wasted retry attempt or extra 1s latency.
- Transient failures retry once with 2s backoff at the model-call level, preserving agent loop state.
- The `SystemContentBlock` list format is a permanent API contract; reverting to a plain string would require updating all callers and tests.
