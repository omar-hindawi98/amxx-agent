"""Main request handler for the GenAI server.

Manages agent invocation, memory updates, and skill loading for each request.
"""

import asyncio
import contextlib
import json
import logging
import re
from pathlib import Path

from strands import Agent

from amxmodx_genai.core import memory
from amxmodx_genai.core.messages import ClearMemoryMsg, QueryMsg
from amxmodx_genai.core.model import make_model
from amxmodx_genai.core.protocol import read_json, send_json
from amxmodx_genai.core.summarize import summarize_session
from amxmodx_genai.skills import load_builtin_skills, load_plugin_skills
from amxmodx_genai.tools import make_plugin_tool, native_tools

log = logging.getLogger(__name__)

_SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / "SYSTEM_PROMPT.md"
_BASE_SYSTEM_PROMPT = (
    _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8") if _SYSTEM_PROMPT_PATH.exists() else ""
)

_MAX_RETRIES = 1

# Loaded once at import time; None when no built-in skills exist.
_BUILTIN_SKILLS = load_builtin_skills()


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Handle a single client connection, process request, and send response."""
    addr = writer.get_extra_info("peername")
    try:
        msg = await read_json(reader, timeout=10.0)
        if msg is None:
            return

        if msg.get("type") == "clear_memory":
            req = ClearMemoryMsg.model_validate(msg)
            session_id = req.session_id or str(req.player)
            history = await asyncio.to_thread(memory.get, session_id)
            if history:
                prior = await asyncio.to_thread(memory.get_longterm, session_id)
                try:
                    summary = await summarize_session(history, prior)
                    if summary:
                        await asyncio.to_thread(memory.set_longterm, session_id, summary)
                        log.info("updated long-term memory for session %s", session_id)
                except Exception as exc:
                    log.warning("summarization failed for session %s: %s", session_id, exc)
            await asyncio.to_thread(memory.clear, session_id)
            log.info("cleared short-term memory for session %s", session_id)
            return

        req = QueryMsg.model_validate(msg)
        player_id = req.player
        session_id = req.session_id or str(player_id)
        prompt = req.prompt
        plugin_name = req.plugin
        plugin_context = req.system
        skill_names = req.skills

        if not prompt:
            send_json(writer, {"type": "response", "text": "(empty prompt)"})
            send_json(writer, {"type": "done"})
            await writer.drain()
            return

        # Prefetch both memory tiers concurrently while building tool list.
        memory_task = asyncio.create_task(asyncio.to_thread(memory.get, session_id))
        longterm_task = asyncio.create_task(asyncio.to_thread(memory.get_longterm, session_id))

        session_data: dict = {}
        plugin_tools = [
            make_plugin_tool(
                t.name,
                t.description,
                reader,
                writer,
                session_data,
                params=t.params or None,
            )
            for t in req.tools
            if t.name and t.description
        ]

        player_history = await memory_task
        longterm = await longterm_task

        full_system = _build_system_prompt(plugin_name, plugin_context, longterm)

        plugins = []
        if _BUILTIN_SKILLS:
            plugins.append(_BUILTIN_SKILLS)
        if skill_names:
            plugin_skills = load_plugin_skills(skill_names)
            if plugin_skills:
                plugins.append(plugin_skills)

        agent_kwargs: dict = {
            "model": make_model(),
            "system_prompt": full_system,
            "tools": plugin_tools + native_tools,
            "messages": player_history,
        }
        if plugins:
            agent_kwargs["plugins"] = plugins

        result = await _invoke_with_retry(agent_kwargs, prompt)

        final_text = ""
        result_msg = getattr(result, "message", None)
        if result_msg:
            content = (
                result_msg.get("content", [])
                if isinstance(result_msg, dict)
                else getattr(result_msg, "content", [])
            )
            for block in content:
                text = (
                    block.get("text", "") if isinstance(block, dict) else getattr(block, "text", "")
                )
                if text:
                    final_text += text

        clean_text = final_text.strip().replace("\n", " ").strip()
        if not clean_text:
            log.warning("agent returned no text for session=%s", session_id)
            clean_text = "(no response)"

        await asyncio.to_thread(memory.update, session_id, prompt, clean_text)

        send_json(writer, {"type": "response", "text": clean_text})
        send_json(writer, {"type": "done"})
        await writer.drain()

        log.info(
            "session=%s player=%d tools_called=%d response_len=%d",
            session_id,
            player_id,
            len(session_data.get("calls", [])),
            len(clean_text),
        )

    except TimeoutError:
        log.warning("timeout from %s", addr)
        _send_error(writer, "(request timed out)")
    except json.JSONDecodeError as e:
        log.warning("bad JSON from %s: %s", addr, e)
        _send_error(writer, "(invalid request)")
    except Exception as e:
        log.exception("unexpected error from %s: %s", addr, e)
        _send_error(writer, "(AI unavailable)")
    finally:
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()


async def _invoke_with_retry(agent_kwargs: dict, prompt: str):
    """Invoke a fresh agent with one retry on failure."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return await Agent(**agent_kwargs).invoke_async(prompt)
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                log.warning("invoke attempt %d failed (%s), retrying", attempt + 1, exc)
                await asyncio.sleep(1.0)
    raise last_exc  # type: ignore[misc]


def _build_system_prompt(plugin_name: str, plugin_context: str, longterm: str = "") -> str:
    """Build the complete system prompt from base, plugin context, and long-term memory."""
    parts = [_BASE_SYSTEM_PROMPT]
    if longterm:
        parts.append(f"\n## Memory from previous sessions\n\n{longterm}")
    if plugin_context:
        heading = f"## {plugin_name}" if plugin_name else "## Plugin context"
        parts.append(f"\n{heading}\n\n{_shift_headings(plugin_context)}")
    return "".join(parts)


def _shift_headings(text: str) -> str:
    """Shift all markdown headings down two levels (# -> ###, ## -> ####, etc.).

    The plugin's section is introduced at ## so its internal headings must
    start at ### to nest correctly without conflicting with the base prompt.
    Headings at level 5 or 6 are capped at ######.
    """
    return re.sub(
        r"^(#{1,6})\s",
        lambda m: "#" * min(len(m.group(1)) + 2, 6) + " ",
        text,
        flags=re.MULTILINE,
    )


def _send_error(writer: asyncio.StreamWriter, text: str) -> None:
    """Send error response and done message to client."""
    with contextlib.suppress(Exception):
        send_json(writer, {"type": "response", "text": text})
        send_json(writer, {"type": "done"})
