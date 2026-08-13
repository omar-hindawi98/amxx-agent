"""Async TCP server for handling GenAI requests."""

import asyncio
import contextlib
import json
import logging
import signal
from typing import Any

from amxmodx_genai.core.handler import handle
from amxmodx_genai.core.model import validate as validate_model
from amxmodx_genai.core.protocol import send_json
from amxmodx_genai.config import settings

log = logging.getLogger(__name__)

_active_tasks: set[asyncio.Task] = set()
_sem: asyncio.Semaphore | None = None


async def _handle_persistent(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    """Handle a persistent connection from the game server plugin.

    Multiple queries arrive over the same TCP connection, each tagged with a
    request_id for multiplexing.  tool_result messages are routed back to the
    in-flight handler that is waiting for them.
    """
    addr = writer.get_extra_info("peername")
    log.info("plugin connected from %s", addr)

    write_lock = asyncio.Lock()
    # Maps request_id -> Queue where tool_result frames are delivered.
    result_queues: dict[str, asyncio.Queue] = {}
    in_flight: set[asyncio.Task] = set()

    async def send(obj: dict[str, Any]) -> None:
        async with write_lock:
            send_json(writer, obj)
            await writer.drain()

    try:
        while True:
            line = await reader.readline()
            if not line:
                break

            try:
                msg = json.loads(line.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                log.warning("bad JSON from %s, skipping frame", addr)
                continue

            msg_type = msg.get("type")
            request_id = msg.get("request_id", "")

            if msg_type == "tool_result":
                q = result_queues.get(request_id)
                if q:
                    await q.put(msg)
                else:
                    log.warning(
                        "no handler waiting for tool_result request_id=%s from %s",
                        request_id,
                        addr,
                    )

            elif msg_type in ("query", "clear_memory"):
                q: asyncio.Queue = asyncio.Queue()
                result_queues[request_id] = q
                task = asyncio.create_task(
                    _bounded_handle(msg, send, q),
                    name=f"handle-{request_id}",
                )
                in_flight.add(task)

                def _done(t: asyncio.Task, rid: str = request_id) -> None:
                    in_flight.discard(t)
                    result_queues.pop(rid, None)

                task.add_done_callback(_done)

            else:
                log.warning("unknown message type %r from %s", msg_type, addr)

    finally:
        log.info("plugin disconnected from %s, cancelling %d in-flight tasks", addr, len(in_flight))
        for t in in_flight:
            t.cancel()
        if in_flight:
            await asyncio.gather(*list(in_flight), return_exceptions=True)
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()


async def _bounded_handle(
    msg: dict[str, Any],
    send: Any,
    tool_result_queue: asyncio.Queue,
) -> None:
    assert _sem is not None
    async with _sem:
        await handle(msg, send, tool_result_queue)


async def _track(coro: Any) -> None:
    task = asyncio.current_task()
    if task is not None:
        _active_tasks.add(task)
    try:
        await coro
    finally:
        if task is not None:
            _active_tasks.discard(task)


async def serve() -> None:
    """Start the GenAI TCP server and listen indefinitely."""
    global _sem
    validate_model()

    if not settings.skills_path.exists():
        log.warning("skills path does not exist: %s", settings.skills_path)

    _sem = asyncio.Semaphore(settings.max_concurrent)

    async def _handler(r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        await _track(_handle_persistent(r, w))

    server = await asyncio.start_server(_handler, settings.host, settings.port)
    addrs = ", ".join(str(s.getsockname()) for s in server.sockets)
    log.info("GenAI sidecar listening on %s", addrs)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _on_signal() -> None:
        log.info("shutdown signal received, stopping server")
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _on_signal)

    async with server:
        await stop_event.wait()
        server.close()
        await server.wait_closed()
        log.info("server closed, cancelling %d active handlers", len(_active_tasks))
        for t in list(_active_tasks):
            t.cancel()
        if _active_tasks:
            await asyncio.gather(*list(_active_tasks), return_exceptions=True)
        log.info("shutdown complete")


def serve_cli() -> None:
    """Configure logging and run the server from CLI."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(serve())
