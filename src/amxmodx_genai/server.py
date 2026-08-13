"""Async TCP server for handling GenAI requests."""

import asyncio
import logging
import signal

from amxmodx_genai.config import settings
from amxmodx_genai.core.handler import handle
from amxmodx_genai.core.model import validate as validate_model

log = logging.getLogger(__name__)

_active_tasks: set[asyncio.Task] = set()
_sem: asyncio.Semaphore | None = None


async def _handle_with_tracking(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    assert _sem is not None
    async with _sem:
        task = asyncio.current_task()
        if task is not None:
            _active_tasks.add(task)
        try:
            await handle(reader, writer)
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

    server = await asyncio.start_server(_handle_with_tracking, settings.host, settings.port)
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
        log.info("server closed, draining %d active handlers", len(_active_tasks))
        if _active_tasks:
            await asyncio.gather(*list(_active_tasks), return_exceptions=True)
        log.info("shutdown complete")


def serve_cli() -> None:
    """Configure logging and run the server from CLI."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(serve())
