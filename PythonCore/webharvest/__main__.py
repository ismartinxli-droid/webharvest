"""Entry point: `python -m webharvest` reads JSON commands from stdin, writes events to stdout."""
import asyncio
import json
import sys
from pathlib import Path

from .cli import dispatch
from .protocol import emit


async def stdin_reader(queue: asyncio.Queue) -> None:
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader(loop=loop)
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    while True:
        line = await reader.readline()
        if not line:
            await queue.put(None)
            return
        await queue.put(line.decode("utf-8", errors="replace").strip())


async def main() -> None:
    queue: asyncio.Queue = asyncio.Queue()
    reader_task = asyncio.create_task(stdin_reader(queue))
    emit("ready")
    while True:
        raw = await queue.get()
        if raw is None:
            return
        try:
            cmd = json.loads(raw)
        except json.JSONDecodeError as e:
            emit("error", {"message": f"invalid json: {e}"})
            continue
        try:
            await dispatch(cmd)
        except Exception as e:  # noqa: BLE001
            emit("error", {"message": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
