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
        p = urlparse(self.path)
        return p.path or "/"

    def _content_type(self, path: str) -> tuple[str, int]:
        # Returns (content_type, status_code)
        if path in ("/", "/index.html"):
            return ("text/html; charset=utf-8", 200)
        if path == "/page2.html":
            return ("text/html; charset=utf-8", 200)
        if path.endswith((".jpg", ".jpeg")):
            return ("image/jpeg", 200)
        if path.endswith(".png"):
            return ("image/png", 200)
        if path.endswith(".webp"):
            return ("image/webp", 200)
        if path.endswith(".pdf"):
            return ("application/pdf", 200)
        if path.endswith(".mp4"):
            return ("video/mp4", 200)
        return ("text/plain", 404)

    def _body(self, path: str) -> bytes:
        ct, status = self._content_type(path)
        if status == 200:
            if ct.startswith("text/html"):
                if path == "/page2.html":
                    return PAGE2_HTML.encode()
                return INDEX_HTML.encode()
            return b"\x00" * 32
        return b"not found"

    def _respond(self, include_body: bool = True) -> None:
        path = self._path()
        ct, status = self._content_type(path)
        body = self._body(path)
        self.send_response(status)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def do_HEAD(self) -> None:  # noqa: N802
        self._respond(include_body=False)

    def do_GET(self) -> None:  # noqa: N802
        self._respond(include_body=True)

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

    # New spider uses content-type to name files, file names may differ
    assert len(images) >= 3, f"Expected >=3 images, got {len(images)}: {[p.name for p in images]}"
    assert len(videos) >= 1, f"Expected >=1 video, got {len(videos)}: {[p.name for p in videos]}"
    assert len(pdfs) >= 1, f"Expected >=1 pdf, got {len(pdfs)}: {[p.name for p in pdfs]}"

    done = [e for e in events if e["event"] == "done"]
    assert done and done[0]["downloaded"] == 5 and done[0]["failed"] == 0
