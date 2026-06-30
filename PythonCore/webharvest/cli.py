"""Command dispatcher: maps incoming JSON commands to async handlers."""
import asyncio
from typing import Any

from .crawler import run as run_crawl
from .protocol import emit

_task: asyncio.Task | None = None


async def dispatch(cmd: dict[str, Any]) -> None:
    global _task
    kind = cmd.get("cmd")
    if kind == "start":
        if _task and not _task.done():
            emit("error", message="crawl already running")
            return
        max_depth = int(cmd.get("max_depth", 3))
        max_depth = max(1, min(5, max_depth))
        _task = asyncio.create_task(
            run_crawl(
                url=cmd["url"],
                types=set(cmd["types"]),
                save_path=cmd["save_path"],
                max_depth=max_depth,
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
