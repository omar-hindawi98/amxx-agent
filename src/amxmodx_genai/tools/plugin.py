"""Factory for Strands tools that round-trip to AMXMODX plugin callbacks."""

import asyncio
import json
import logging
import uuid
from typing import Any

from strands import tool

log = logging.getLogger(__name__)

# Whitelist of JSON Schema types accepted from Pawn. Unknown types fall back to "string".
_VALID_TYPES: frozenset[str] = frozenset({"string", "integer", "boolean", "number"})


def _build_input_schema(params: list[dict]) -> dict:
    properties: dict = {}
    required: list[str] = []
    for p in params:
        name = p.get("name")
        if not name:
            continue
        json_type = p.get("type", "string") if p.get("type") in _VALID_TYPES else "string"
        prop: dict = {"type": json_type}
        if p.get("description"):
            prop["description"] = p["description"]
        properties[name] = prop
        if p.get("required"):
            required.append(name)
    schema: dict = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


def make_plugin_tool(
    name: str,
    description: str,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    session_data: dict,
    params: list[dict] | None = None,
) -> Any:
    """Return a Strands tool that round-trips a tool_call/tool_result over the open socket.

    params is a list of {"name", "type", "required", "description"} dicts from the
    plugin registration. When provided, Strands receives a typed JSON schema so the
    model uses the correct argument types. When absent, falls back to a single
    free-form args string for backward compatibility.

    session_data is shared across all plugin tools in the same query so the handler
    can observe which tools fired and what they returned.

    Trust boundary: tool result content comes from the AMXMODX plugin callback and is
    returned verbatim to the model. The plugin is trusted; no sanitization is applied.
    """
    if params:
        input_schema = _build_input_schema(params)

        @tool(inputSchema={"json": input_schema})
        async def _fn(**kwargs: Any) -> str:
            args = json.dumps(kwargs)
            return await _call(name, args, reader, writer, session_data)

    else:

        async def _fn(args: str = "{}") -> str:  # type: ignore[misc]
            return await _call(name, args, reader, writer, session_data)

    _fn.__name__ = name
    _fn.__doc__ = description

    if params:
        return _fn
    return tool(_fn)


async def _call(
    name: str,
    args: str,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    session_data: dict,
) -> str:
    call_id = f"plug_{uuid.uuid4().hex[:8]}"
    payload = json.dumps({"type": "tool_call", "id": call_id, "name": name, "args": args})
    writer.write((payload + "\n").encode("utf-8"))
    await writer.drain()

    deadline = asyncio.get_event_loop().time() + 15.0
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            _record(session_data, name, args, None, error="tool call timed out")
            return "(tool call timed out)"
        raw = await asyncio.wait_for(reader.readline(), timeout=remaining)
        if not raw:
            _record(session_data, name, args, None, error="plugin closed connection")
            return "(plugin closed connection)"
        reply = json.loads(raw.decode("utf-8", errors="replace"))
        if reply.get("type") == "tool_result" and reply.get("id") == call_id:
            content = reply.get("content", "")
            _record(session_data, name, args, content)
            return content
        log.warning(
            "discarding unexpected frame type=%s id=%s (expected tool_result id=%s)",
            reply.get("type"),
            reply.get("id"),
            call_id,
        )


def _record(
    session_data: dict,
    name: str,
    args: str,
    result: str | None,
    *,
    error: str | None = None,
) -> None:
    calls: list = session_data.setdefault("calls", [])
    entry: dict = {"tool": name, "args": args}
    if error:
        entry["error"] = error
    else:
        entry["result"] = result
    calls.append(entry)
