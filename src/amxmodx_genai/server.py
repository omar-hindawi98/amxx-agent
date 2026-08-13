"""Async TCP server for handling GenAI requests."""

import asyncio
import logging

from amxmodx_genai.config import settings
from amxmodx_genai.core.handler import handle

log = logging.getLogger(__name__)


async def serve() -> None:
    """Start the GenAI TCP server and listen indefinitely."""
    server = await asyncio.start_server(handle, settings.host, settings.port)
    addrs = ", ".join(str(s.getsockname()) for s in server.sockets)
    log.info("GenAI sidecar listening on %s", addrs)
    async with server:
        await server.serve_forever()


def serve_cli() -> None:
    """Configure logging and run the server from CLI."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(serve())
