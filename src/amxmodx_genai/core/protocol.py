"""Wire protocol helpers: JSON framing."""

import asyncio
import json
from typing import Any


def send_json(writer: asyncio.StreamWriter, obj: dict[str, Any]) -> None:
    writer.write((json.dumps(obj) + "\n").encode("utf-8"))


async def read_json(reader: asyncio.StreamReader, timeout: float = 10.0) -> dict[str, Any] | None:
    raw = await asyncio.wait_for(reader.readline(), timeout=timeout)
    if not raw:
        return None
    return json.loads(raw.decode("utf-8", errors="replace"))
