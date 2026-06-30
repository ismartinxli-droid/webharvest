"""Entry point: `python -m webharvest` reads JSON commands from stdin, writes events to stdout."""
import asyncio
import json
import sys
import threading
from queue import Queue

from .cli import dispatch
from .protocol import emit


def _stdin_thread(queue: Queue) -> None:
    """Read stdin line-by-line in a background thread (avoids asyncio pipe issues)."""
    for line in sys.stdin:
        line = line.strip()
        if line:
            queue.put(line)
    queue.put(None)


async def main() -> None:
    queue: Queue = Queue()
    t = threading.Thread(target=_stdin_thread, args=(queue,), daemon=True)
    t.start()
    emit("ready")
    while True:
        # poll the queue without blocking the event loop
        raw = await asyncio.get_event_loop().run_in_executor(None, queue.get)
        if raw is None:
            return
        try:
            cmd = json.loads(raw)
        except json.JSONDecodeError as e:
            emit("error", message=f"invalid json: {e}")
            continue
        try:
            await dispatch(cmd)
        except Exception as e:
            emit("error", message=f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
