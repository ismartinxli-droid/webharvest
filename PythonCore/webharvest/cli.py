"""Command dispatcher: maps incoming JSON commands to async handlers."""
import asyncio
from typing import Any

from .crawler import run as run_crawl
from .protocol import emit

_loop: asyncio.AbstractEventLoop | None = None
_task: asyncio.Task | None = None


async def dispatch(cmd: dict[str, Any]) -> None:
    global _loop, _task
    kind = cmd.get("cmd")
    if kind == "start":
        if _task and not _task.done():
            emit("error", message="crawl already running")
            return
        _loop = asyncio.get_event_loop()
        _task = asyncio.create_task(
            run_crawl(
                url=cmd["url"],
                types=set(cmd["types"]),
                save_path=cmd["save_path"],
            )
        )
    elif kind == "stop":
        if _task and not _task.done():
            _task.cancel()
        emit("phase", name="stopped")
    elif kind == "ping":
        emit("ready")
    else:
        emit("error", message=f"unknown cmd: {kind!r}")
