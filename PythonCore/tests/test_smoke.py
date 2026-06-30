"""End-to-end smoke test: spin up a local HTTP server with a tiny site,
run the crawler, verify assets land in the right folders."""
from __future__ import annotations

import asyncio
import http.server
import socketserver
import threading
from pathlib import Path

import time

import pytest

from webharvest.crawler.spider import run as run_crawl
from webharvest.protocol import emit

PORT = 0  # OS-assigned, see server fixture
SITE = ""  # populated by server fixture

INDEX_HTML = """<!doctype html>
<html><body>
<h1>Test</h1>
<img src="/assets/photo.jpg">
<img src="/assets/icon.png">
<a href="/page2.html">page 2</a>
<a href="/doc.pdf">pdf</a>
</body></html>"""

PAGE2_HTML = """<!doctype html>
<html><body>
<img src="/assets/banner.webp">
<video src="/assets/clip.mp4"></video>
</body></html>"""


from urllib.parse import urlparse

class Handler(http.server.BaseHTTPRequestHandler):
    def _path(self) -> str:
        # httpx sends absolute-form requests, so self.path may be the full URL.
        # Strip scheme://host so we can compare against test paths.
        p = urlparse(self.path)
        return p.path or "/"

    def do_GET(self) -> None:  # noqa: N802
        path = self._path()
        if path == "/" or path == "/index.html":
            body = INDEX_HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        elif path == "/page2.html":
            body = PAGE2_HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        elif path.endswith((".jpg", ".png", ".webp", ".pdf", ".mp4")):
            body = b"\x00" * 32
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            body = b"not found"
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: object) -> None:  # silence stderr
        return


class ReusableTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


@pytest.fixture(scope="module")
def server():
    httpd = ReusableTCPServer(("127.0.0.1", 0), Handler)
    httpd.daemon_threads = True
    actual_port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    time.sleep(0.2)
    yield f"http://127.0.0.1:{actual_port}"
    httpd.shutdown()
    httpd.server_close()


def test_crawl_downloads_assets(tmp_path: Path, server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[dict] = []

    def capture(event: str, **kw):
        events.append({"event": event, **kw})
        real_emit(event, **kw)

    import webharvest.protocol
    real_emit = webharvest.protocol.emit
    monkeypatch.setattr("webharvest.protocol.emit", capture)
    # also rebind in any modules that did `from .protocol import emit`
    import webharvest.crawler.spider as spider_mod
    monkeypatch.setattr(spider_mod, "emit", capture)

    asyncio.run(run_crawl(server, {"image", "video", "pdf"}, str(tmp_path)))

    images = list((tmp_path / "images").glob("*"))
    videos = list((tmp_path / "videos").glob("*"))
    pdfs = list((tmp_path / "pdfs").glob("*"))

    assert {p.name for p in images} == {"photo.jpg", "icon.png", "banner.webp"}
    assert {p.name for p in videos} == {"clip.mp4"}
    assert {p.name for p in pdfs} == {"doc.pdf"}

    done = [e for e in events if e["event"] == "done"]
    assert done and done[0]["downloaded"] == 5 and done[0]["failed"] == 0
