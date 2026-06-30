"""URL frontier: FIFO queue with dedup-by-hash for the BFS crawl."""
from collections import deque
from hashlib import sha1
from urllib.parse import urlparse, urlunparse


class UrlFrontier:
    """Breadth-first URL queue. Strips fragments and tracks visited set."""

    def __init__(self, seed: str) -> None:
        self._queue: deque[str] = deque()
        self._seen: set[str] = set()
        self.push(seed)

    def push(self, url: str) -> None:
        clean = _canonicalize(url)
        if not clean:
            return
        h = sha1(clean.encode()).hexdigest()
        if h in self._seen:
            return
        self._seen.add(h)
        self._queue.append(clean)

    def pop_batch(self, n: int) -> list[str]:
        out: list[str] = []
        for _ in range(min(n, len(self._queue))):
            out.append(self._queue.popleft())
        return out

    def empty(self) -> bool:
        return not self._queue


def _canonicalize(url: str) -> str:
    try:
        p = urlparse(url)
    except ValueError:
        return ""
    if not p.scheme or not p.netloc:
        return ""
    if p.scheme not in ("http", "https"):
        return ""
    return urlunparse((p.scheme, p.netloc.lower(), p.path or "/", p.params, p.query, ""))
