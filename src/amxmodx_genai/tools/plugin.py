"""Factory for Strands tools that round-trip to AMXMODX plugin callbacks."""

import asyncio
import json
import logging
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

from pydantic import BaseModel, field_validator
from strands import tool

log = logging.getLogger(__name__)

# Whitelist of JSON Schema types accepted from Pawn. Unknown types fall back to "string".
_VALID_TYPES: frozenset[str] = frozenset({"string", "integer", "boolean", "number"})

# Cap plugin tool results to prevent accidental huge payloads being forwarded to the model.
_MAX_TOOL_RESULT_BYTES = 8192


class _ToolParam(BaseModel):
    """A single typed parameter in a plugin tool definition."""

    name: str
    type: str = "string"
    required: bool = False
    description: str = ""

    @field_validator("type", mode="before")
    @classmethod
    def _coerce_type(cls, v: object) -> str:
        """Fall back to string for any JSON Schema type not supported by Pawn."""
        return str(v) if str(v) in _VALID_TYPES else "string"


def _build_input_schema(params: list[_ToolParam | dict]) -> dict:
    """Build a JSON Schema object from validated Pawn parameter definitions."""
    properties: dict = {}
    required: list[str] = []
    for raw in params:
        try:
            p = _ToolParam.model_validate(raw) if isinstance(raw, dict) else raw
        except Exception:
            continue
        prop: dict = {"type": p.type}
        if p.description:
            prop["description"] = p.description
        properties[p.name] = prop
        if p.required:
            required.append(p.name)
    schema: dict = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


def make_plugin_tool(
    name: str,
    description: str,
    send: Callable[[dict], Coroutine],
    tool_result_queue: asyncio.Queue,
    request_id: str,
    session_data: dict,
    params: list[dict] | None = None,
) -> Any:
    """Return a Strands tool that round-trips a tool_call/tool_result over the persistent socket.

    send is an async callable that writes one JSON message to the shared connection.
    tool_result_queue receives tool_result messages routed by the server for this request_id.

    Trust boundary: tool result content comes from the AMXMODX plugin callback and is
    returned verbatim to the model. The plugin is trusted; no sanitization is applied.
    """
    validated = [_ToolParam.model_validate(p) for p in params] if params else None
    if validated:
        input_schema = _build_input_schema(validated)

        @tool(inputSchema={"json": input_schema})
        async def _fn(**kwargs: Any) -> str:
            args = json.dumps(kwargs)
            return await _call(name, args, send, tool_result_queue, request_id, session_data)

    else:

        @tool
        async def _fn(args: str = "{}") -> str:  # type: ignore[misc]
            return await _call(name, args, send, tool_result_queue, request_id, session_data)

    _fn.__name__ = name
    _fn.__doc__ = description

    return _fn


async def _call(
    name: str,
    args: str,
    send: Callable[[dict], Coroutine],
    tool_result_queue: asyncio.Queue,
    request_id: str,
    session_data: dict,
) -> str:
    """Send tool call to plugin, wait for result from the routed queue, and return content."""
    call_id = f"plug_{uuid.uuid4().hex[:8]}"
    await send(
        {
            "type": "tool_call",
            "request_id": request_id,
            "id": call_id,
            "name": name,
            "args": args,
        }
    )

    deadline = asyncio.get_running_loop().time() + 15.0
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            _record(session_data, name, args, None, error="tool call timed out")
            return "(tool call timed out)"
        try:
            reply = await asyncio.wait_for(tool_result_queue.get(), timeout=remaining)
        except TimeoutError:
            _record(session_data, name, args, None, error="tool call timed out")
            return "(tool call timed out)"
        if reply.get("id") == call_id:
            content = reply.get("content", "")
            if isinstance(content, str) and len(content) > _MAX_TOOL_RESULT_BYTES:
                log.warning(
                    "tool result from %s truncated (%d -> %d bytes)",
                    name,
                    len(content),
                    _MAX_TOOL_RESULT_BYTES,
                )
                content = content[:_MAX_TOOL_RESULT_BYTES]
            _record(session_data, name, args, content)
            return content
        # Unexpected id (shouldn't happen; tool calls within one request are sequential).
        await tool_result_queue.put(reply)
        await asyncio.sleep(0)


def _record(
    session_data: dict,
    name: str,
    args: str,
    result: str | None,
    *,
    error: str | None = None,
) -> None:
    """Record tool call outcome to session data."""
    calls: list = session_data.setdefault("calls", [])
    entry: dict = {"tool": name, "args": args}
    if error:
        entry["error"] = error
    else:
        entry["result"] = result
    calls.append(entry)
