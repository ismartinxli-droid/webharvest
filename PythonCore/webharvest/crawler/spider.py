"""BFS site crawler: discovers pages, extracts assets, downloads them in parallel."""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
import tldextract
from selectolax.parser import HTMLParser

from ..config import IMAGE_EXTS, PDF_EXTS, VIDEO_EXTS
from ..downloader import download
from ..protocol import emit
from .url_frontier import UrlFrontier

# cap concurrent network tasks to stay friendly and avoid hammering the host
_MAX_CONCURRENT = 16
_REQUEST_TIMEOUT = 20.0
_MAX_PAGES = 5000


async def run(url: str, types: set[str], save_path: str) -> None:
    """Crawl the same-domain pages rooted at `url` and download all matching assets."""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        emit("error", message=f"invalid url: {url}")
        return
    base_host = _registered_host(parsed.netloc)

    exts: set[str] = set()
    if "image" in types:
        exts |= IMAGE_EXTS
    if "video" in types:
        exts |= VIDEO_EXTS
    if "pdf" in types:
        exts |= PDF_EXTS
    if not exts:
        emit("error", message="no file types selected")
        return

    save_root = Path(save_path).expanduser()
    save_root.mkdir(parents=True, exist_ok=True)

    emit("phase", name="crawling")
    frontier = UrlFrontier(seed=url)
    seen_pages: set[str] = set()
    seen_assets: set[str] = set()
    downloaded = 0
    failed = 0
    sem = asyncio.Semaphore(_MAX_CONCURRENT)

    async with httpx.AsyncClient(
        timeout=_REQUEST_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": "WebHarvest/0.1 (+https://webharvest.app)"},
    ) as client:

        async def process_page(page_url: str) -> None:
            nonlocal downloaded, failed
            try:
                async with sem:
                    resp = await client.get(page_url)
                if resp.status_code != 200 or "text/html" not in resp.headers.get("content-type", ""):
                    return
            except Exception as e:  # noqa: BLE001
                emit("phase", name=f"page error: {page_url} ({e})")
                return

            html = HTMLParser(resp.text)
            new_links: list[str] = []
            for a in html.css("a[href]"):
                href = a.attributes.get("href")
                if not href or href.startswith(("#", "javascript:", "mailto:")):
                    continue
                abs_url = urljoin(page_url, href.split("#")[0])
                if _same_host(abs_url, base_host):
                    new_links.append(abs_url)

            asset_urls: list[tuple[str, str]] = []
            for img in html.css("img[src]"):
                src = img.attributes.get("src")
                if src:
                    asset_urls.append((urljoin(page_url, src), "image"))
            for src_attr in ("src", "data-src"):
                for v in html.css(f"video[{src_attr}], video source[{src_attr}]"):
                    s = v.attributes.get(src_attr)
                    if s:
                        asset_urls.append((urljoin(page_url, s), "video"))
            for a in html.css("a[href$='.pdf'], a[href*='.pdf?']"):
                h = a.attributes.get("href")
                if h:
                    asset_urls.append((urljoin(page_url, h), "pdf"))

            for link in new_links:
                if link not in seen_pages:
                    seen_pages.add(link)
                    frontier.push(link)
            emit("pages.crawled", count=len(seen_pages))

            for asset_url, ftype in asset_urls:
                if asset_url in seen_assets:
                    continue
                if not _has_matching_ext(asset_url, exts):
                    continue
                seen_assets.add(asset_url)
                emit("asset.queued", type=ftype, url=asset_url)
                ok, size_or_err = await download(client, asset_url, ftype, save_root)
                if ok:
                    downloaded += 1
                    emit("asset.downloaded", type=ftype, path=size_or_err, size=0)
                else:
                    failed += 1
                    emit("asset.failed", type=ftype, url=asset_url, error=size_or_err)

        while not frontier.empty() and len(seen_pages) < _MAX_PAGES:
            batch = frontier.pop_batch(32)
            await asyncio.gather(*(process_page(u) for u in batch))

    emit("done", downloaded=downloaded, failed=failed)


def _registered_host(netloc: str) -> str:
    """Return eTLD+1 (e.g. 'example.com') for cross-subdomain matching.

    Falls back to the full netloc for bare IPs / localhost / unknown TLDs.
    """
    # strip port for tldextract; it doesn't understand 'host:port'
    host_only = netloc.split(":", 1)[0]
    ext = tldextract.extract(host_only)
    return ext.top_domain_under_public_suffix or host_only


def _same_host(url: str, base: str) -> bool:
    host = urlparse(url).netloc
    if not host:
        return False
    return _registered_host(host) == base


def _has_matching_ext(url: str, exts: set[str]) -> bool:
    path = urlparse(url).path.lower()
    for ext in exts:
        if path.endswith(f".{ext}"):
            return True
    return False
