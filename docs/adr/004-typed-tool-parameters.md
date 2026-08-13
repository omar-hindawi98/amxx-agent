# ADR 004: Typed tool parameters via builder pattern

## Status

Accepted

## Context

Strands tools require a JSON Schema `inputSchema` so the model receives proper type constraints. Without a schema, the model guesses argument format from the description and often passes wrong types or omits required fields. Pawn (the AMXMODX scripting language) has no native JSON Schema support and no dynamic data structures suitable for building a schema object at runtime. Having plugin authors write raw JSON schema strings in Pawn constants is fragile and verbose.

## Decision

Use a builder pattern: `genai_register_tool` registers the tool and sets it as the current tool being built. Subsequent `genai_add_tool_param(name, type, required, description)` calls append parameters to it. The sidecar converts the accumulated parameter list into a proper JSON Schema `inputSchema` when the tool is first used.

Supported types: `"string"`, `"integer"`, `"boolean"`, `"number"`.

## Consequences

- Plugin authors declare parameters in a natural, linear style without writing JSON.
- The model receives proper type constraints and required/optional distinctions.
- The "current tool" state means `genai_add_tool_param` must be called immediately after `genai_register_tool`, before any other `genai_register_tool` call. This is documented but not enforced at runtime.
- Tools with no `genai_add_tool_param` calls are valid (zero-parameter tools).
