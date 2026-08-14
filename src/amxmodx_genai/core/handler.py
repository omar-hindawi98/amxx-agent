"""Main request handler for the GenAI server.

Manages agent invocation, memory updates, and skill loading for each request.
"""

import asyncio
import contextlib
import json
import logging
import re
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from strands import Agent
from strands.hooks import AfterModelCallEvent, BeforeInvocationEvent, HookProvider, HookRegistry
from strands.types.content import SystemContentBlock
from strands.types.exceptions import ContextWindowOverflowException, MaxTokensReachedException

from amxmodx_genai.config import settings
from amxmodx_genai.core import memory
from amxmodx_genai.core.messages import ClearLongtermMsg, ClearMemoryMsg, QueryMsg
from amxmodx_genai.core.model import get_model
from amxmodx_genai.core.summarize import summarize_session
from amxmodx_genai.skills import load_builtin_skills, load_plugin_skills
from amxmodx_genai.tools import make_plugin_tool, native_tools

log = logging.getLogger(__name__)

_SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / "SYSTEM_PROMPT.md"
try:
    _BASE_SYSTEM_PROMPT = (
        _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8") if _SYSTEM_PROMPT_PATH.exists() else ""
    )
except OSError as _exc:
    log.warning("could not read system prompt from %s: %s", _SYSTEM_PROMPT_PATH, _exc)
    _BASE_SYSTEM_PROMPT = ""

_MAX_HOOK_RETRIES = 1

# Loaded once at import time; None when no built-in skills exist or loading fails.
try:
    _BUILTIN_SKILLS = load_builtin_skills()
except Exception as _exc:
    log.warning("failed to load built-in skills: %s", _exc)
    _BUILTIN_SKILLS = None

_UNRECOVERABLE = (MaxTokensReachedException, ContextWindowOverflowException)


class _RetryHook(HookProvider):
    """Retry transient model-call failures with exponential backoff."""

    def __init__(self) -> None:
        self._count = 0

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeInvocationEvent, self._reset)
        registry.add_callback(AfterModelCallEvent, self._maybe_retry)

    def _reset(self, event: BeforeInvocationEvent) -> None:
        self._count = 0

    async def _maybe_retry(self, event: AfterModelCallEvent) -> None:
        if not event.exception or isinstance(event.exception, _UNRECOVERABLE):
            return
        if self._count < _MAX_HOOK_RETRIES:
            self._count += 1
            log.warning("model call failed (%s), retry %d/%d", event.exception, self._count, _MAX_HOOK_RETRIES)
            event.retry = True
            await asyncio.sleep(2.0**self._count)


# Type alias for the send callable passed in by the server.
_Send = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


async def handle(
    msg: dict[str, Any],
    send: _Send,
    tool_result_queue: asyncio.Queue,
) -> None:
    """Handle one request from the persistent connection.

    msg      - already-parsed JSON dict from the plugin
    send     - async callable that writes one JSON object to the shared socket (thread-safe)
    tool_result_queue - asyncio.Queue that receives tool_result messages routed for this request
    """
    request_id = msg.get("request_id", "")

    async def _send(obj: dict[str, Any]) -> None:
        await send({**obj, "request_id": request_id})

    if settings.auth_token and msg.get("auth_token") != settings.auth_token:
        log.warning("unauthorized request (request_id=%s)", request_id)
        await _safe_send_error(_send, "(unauthorized)")
        return

    try:
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

        if msg.get("type") == "clear_longterm":
            req = ClearLongtermMsg.model_validate(msg)
            session_id = req.session_id or str(req.player)
            await asyncio.to_thread(memory.clear_longterm, session_id)
            log.info("cleared long-term memory for session %s", session_id)
            return

        req = QueryMsg.model_validate(msg)
        player_id = req.player
        session_id = req.session_id or str(player_id)
        prompt = req.prompt
        plugin_name = req.plugin
        plugin_context = req.system
        skill_names = req.skills

        if not prompt:
            await _send({"type": "response", "text": "(empty prompt)", "status": "error"})
            await _send({"type": "done"})
            return

        # Prefetch both memory tiers concurrently while building tool list.
        memory_task = asyncio.create_task(asyncio.to_thread(memory.get, session_id))
        longterm_task = asyncio.create_task(asyncio.to_thread(memory.get_longterm, session_id))

        session_data: dict = {}
        plugin_tools = [
            make_plugin_tool(
                t.name,
                t.description,
                _send,
                tool_result_queue,
                request_id,
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
            try:
                plugin_skills = load_plugin_skills(skill_names)
                if plugin_skills:
                    plugins.append(plugin_skills)
            except Exception as exc:
                log.warning("failed to load plugin skills %s: %s", skill_names, exc)

        agent_kwargs: dict = {
            "name": "amxmodx-genai",
            "model": get_model(),
            "system_prompt": full_system,
            "tools": plugin_tools + (native_tools if settings.model_backend != "ollama" else []),
            "messages": player_history,
            "callback_handler": None,
            "hooks": [_RetryHook()],
        }
        if plugins:
            agent_kwargs["plugins"] = plugins

        timeout = settings.request_timeout_seconds or None
        result = await asyncio.wait_for(
            Agent(**agent_kwargs).invoke_async(prompt), timeout=timeout
        )

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

        await _send({"type": "response", "text": clean_text, "status": "ok"})
        await _send({"type": "done"})

        metrics = getattr(result, "metrics", None)
        usage = getattr(metrics, "accumulated_usage", {}) if metrics else {}
        log.info(
            "session=%s player=%d tools_called=%d response_len=%d tokens=%d",
            session_id,
            player_id,
            len(session_data.get("calls", [])),
            len(clean_text),
            usage.get("totalTokens", 0),
        )

    except MaxTokensReachedException:
        log.warning("max tokens reached (request_id=%s)", request_id)
        await _safe_send_error(_send, "(response too long)")
    except ContextWindowOverflowException:
        log.warning("context window overflow (request_id=%s)", request_id)
        await _safe_send_error(_send, "(conversation too long, try clearing memory)")
    except TimeoutError:
        log.warning("request timed out (request_id=%s)", request_id)
        await _safe_send_error(_send, "(request timed out)")
    except json.JSONDecodeError as e:
        log.warning("bad JSON in request (request_id=%s): %s", request_id, e)
        await _safe_send_error(_send, "(invalid request)")
    except Exception as e:
        log.exception("unexpected error (request_id=%s): %s", request_id, e)
        await _safe_send_error(_send, "(AI unavailable)")


def _build_system_prompt(
    plugin_name: str, plugin_context: str, longterm: str = ""
) -> list[SystemContentBlock]:
    """Build the system prompt as a SystemContentBlock list with a cache point.

    Static content (base prompt + plugin context) sits before the cache point so
    Anthropic can cache it across requests from the same plugin. Dynamic content
    (long-term memory) goes after the cache point so it never invalidates the cache.
    Other backends accept list[SystemContentBlock] and ignore the cachePoint entry.
    """
    static = _BASE_SYSTEM_PROMPT
    if plugin_context:
        heading = f"## {plugin_name}" if plugin_name else "## Plugin context"
        static += f"\n{heading}\n\n{_shift_headings(plugin_context)}"

    blocks: list[SystemContentBlock] = [
        SystemContentBlock(text=static),
        SystemContentBlock(cachePoint={"type": "default"}),
    ]
    if longterm:
        blocks.append(
            SystemContentBlock(text=f"\n## Memory from previous sessions\n\n{longterm}")
        )
    return blocks


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


async def _safe_send_error(send: _Send, text: str) -> None:
    with contextlib.suppress(Exception):
        await send({"type": "response", "text": text, "status": "error"})
        await send({"type": "done"})
