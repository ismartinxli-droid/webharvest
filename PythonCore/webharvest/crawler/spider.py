"""BFS site crawler: discovers pages, extracts ALL URLs, downloads by content-type.
Uses Playwright for ALL page loads (seed + sub-pages) to bypass WAF detection.
httpx fallback is only used for downloading individual asset URLs."""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote

import httpx
import tldextract

from ..config import FOLDER_BY_TYPE
from ..protocol import emit
from .url_frontier import UrlFrontier

_MAX_CONCURRENT = 6
_REQUEST_TIMEOUT = 15.0
_DOWNLOAD_TIMEOUT = 60.0
_MAX_PAGES = 200
_MAX_ASSETS = 5000
# Content-type prefixes that map to our file types
_CT_IMAGE = ("image/",)
_CT_VIDEO = ("video/",)
_CT_PDF = ("application/pdf",)
_CT_FONT = ("font/", "application/x-font", "application/font")

# Save-body helpers — reused for seed AND sub-pages
from ..config import IMAGE_EXTS, VIDEO_EXTS, FONT_EXTS, PDF_EXTS  # noqa: E402


async def run(url: str, types: set[str], save_path: str, max_depth: int = 3) -> None:
    """Crawl pages up to max_depth levels, download all matching assets.

    Depth semantics (user-visible):
      depth=1 → seed page only (no sub-page crawling)
      depth=2 → seed + sub-pages (links from seed page)
      depth=3 → seed + sub-pages + sub-sub-pages
    """
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        emit("error", message=f"invalid url: {url}")
        return
    base_host = _registered_host(parsed.netloc)

    save_root = Path(save_path).expanduser()
    save_root.mkdir(parents=True, exist_ok=True)

    # Convert user-visible depth to internal BFS depth:
    #   user depth 1 → 0 BFS levels (seed only)
    #   user depth 2 → 1 BFS level (seed + sub-pages)
    #   user depth 3 → 2 BFS levels (seed + 2 levels of sub-pages)
    bfs_depth = max(0, max_depth - 1)

    emit("phase", name=f"crawling (seed + {bfs_depth} sub-level{'s' if bfs_depth != 1 else ''})")

    seen_pages: set[str] = {url}
    seen_assets: set[str] = set()
    downloaded = 0
    failed = 0
    cdn_failed_urls: list[str] = []
    sem = asyncio.Semaphore(_MAX_CONCURRENT)

    # --- Helper: save bodies captured by Playwright ---
    async def _save_playwright_bodies(bodies: dict[str, bytes]) -> int:
        """Write dict[url, bytes] to disk by URL extension. Returns count saved."""
        nonlocal downloaded
        saved = 0
        for asset_url, body in bodies.items():
            if asset_url in seen_assets:
                continue
            seen_assets.add(asset_url)
            url_lower = asset_url.lower()
            ftype = None
            for ext in IMAGE_EXTS:
                if f".{ext}" in url_lower or f".{ext}?" in url_lower:
                    ftype = "image" ; break
            if ftype is None:
                for ext in VIDEO_EXTS:
                    if f".{ext}" in url_lower or f".{ext}?" in url_lower:
                        ftype = "video" ; break
            if ftype is None:
                for ext in FONT_EXTS:
                    if f".{ext}" in url_lower or f".{ext}?" in url_lower:
                        ftype = "font" ; break
            if ftype is None:
                for ext in PDF_EXTS:
                    if f".{ext}" in url_lower or f".{ext}?" in url_lower:
                        ftype = "pdf" ; break
            if ftype is None or ftype not in types:
                continue
            path_part = urlparse(asset_url).path
            name = path_part.rsplit("/", 1)[-1] if "/" in path_part else "asset"
            name = unquote(name)
            name = _safe(name)
            dest_dir = Path(save_path) / FOLDER_BY_TYPE[ftype]
            dest_dir.mkdir(parents=True, exist_ok=True)
            (dest_dir / name).write_bytes(body)
            saved += 1
            emit("asset.downloaded", type=ftype, path=str(dest_dir / name), size=len(body))
        downloaded += saved
        return saved

    # ======================================================================
    # Phase 1: Seed page via Playwright
    # ======================================================================
    browser_urls: set[str] = set()
    browser_cookies: dict[str, str] = {}
    saved_bodies: dict[str, bytes] = {}
    current_sub_pages: set[str] = set()

    try:
        from .browser import extract_asset_urls as browser_extract

        emit("phase", name="launching Chromium...")
        browser_urls, browser_cookies, saved_bodies, current_sub_pages = await browser_extract(url)
        emit("phase", name=f"Chromium found {len(browser_urls)} resources")
    except ImportError:
        emit("phase", name="Playwright not available, using static parser")
    except Exception as e:
        emit("phase", name=f"Playwright failed ({e}), using static parser")

    # --- Save seed bodies ---
    saved_seed = await _save_playwright_bodies(saved_bodies)
    emit("phase", name=f"Saved {saved_seed} assets from seed page")

    # --- Download remaining seed URLs via httpx ---
    # Build httpx client with cookies from Playwright session
    client_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": url.rstrip("/") + "/",
    }
    cookie_domain = parsed.netloc.split(":")[0]
    client_cookies_h = None
    if browser_cookies:
        client_cookies_h = httpx.Cookies()
        for name, value in browser_cookies.items():
            client_cookies_h.set(name, value, domain=cookie_domain)

    async with httpx.AsyncClient(
        timeout=_REQUEST_TIMEOUT,
        follow_redirects=True,
        headers=client_headers,
        cookies=client_cookies_h,
    ) as client:

        async def try_download(asset_url: str) -> None:
            nonlocal downloaded, failed
            if asset_url in seen_assets or len(seen_assets) > _MAX_ASSETS:
                return
            seen_assets.add(asset_url)
            if asset_url.startswith("data:"):
                return
            try:
                async with sem:
                    resp = await client.get(asset_url, timeout=_DOWNLOAD_TIMEOUT)
                if resp.status_code != 200:
                    failed += 1
                    if resp.status_code == 567:
                        cdn_failed_urls.append(asset_url)
                    emit("asset.failed", type="image", url=asset_url, error=f"HTTP {resp.status_code}")
                    return
                ct = (resp.headers.get("content-type") or "").lower()
                body = resp.content
                if not body:
                    failed += 1
                    emit("asset.failed", type="image", url=asset_url, error="empty response")
                    return
                ftype = None
                if any(ct.startswith(p) for p in _CT_IMAGE):
                    ftype = "image"
                elif any(ct.startswith(p) for p in _CT_VIDEO):
                    ftype = "video"
                elif any(ct.startswith(p) for p in _CT_PDF):
                    ftype = "pdf"
                elif any(ct.startswith(p) for p in _CT_FONT):
                    ftype = "font"
                if ftype is None or ftype not in types:
                    failed += 1
                    emit("asset.failed", type="image", url=asset_url, error=f"unexpected type: {ct}")
                    return
                name = _filename_for(resp)
                dest_dir = save_root / FOLDER_BY_TYPE[ftype]
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / name
                dest.write_bytes(body)
                downloaded += 1
                emit("asset.downloaded", type=ftype, path=str(dest), size=len(body))
            except Exception as e:
                failed += 1
                emit("asset.failed", type="image", url=asset_url, error=str(e))

        # Download remaining URLs from seed's Playwright discovery
        remaining_urls = [u for u in browser_urls if u not in seen_assets]
        if remaining_urls:
            emit("phase", name=f"Downloading {len(remaining_urls)} remaining assets via HTTP...")
            for asset_url in remaining_urls:
                await try_download(asset_url)

    # ======================================================================
    # Phase 2: Sub-pages via Playwright (same browser context)
    # ======================================================================
    if bfs_depth > 0 and current_sub_pages:
        emit("phase", name=f"Playwright found {len(current_sub_pages)} sub-page links")

        # Filter out already-seen and determine which to crawl each level
        level_pages = [u for u in current_sub_pages if u not in seen_pages]
        for sp in level_pages:
            seen_pages.add(sp)

        emit("phase", name=f"Processing {len(level_pages)} sub-pages via Playwright...")

        try:
            from playwright.async_api import async_playwright
            from .browser import extract_sub_page_assets

            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    channel="chrome", headless=True,
                    args=["--no-sandbox","--disable-blink-features=AutomationControlled",
                          "--disable-web-security","--allow-running-insecure-content",
                          "--window-size=1920,1080"],
                )
                p_context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    viewport={"width": 1920, "height": 1080},
                    locale="zh-CN", timezone_id="Asia/Shanghai",
                )

                # Level 1: process seed's sub-pages
                current_depth = 0
                current_batch = level_pages
                while current_depth < bfs_depth and current_batch:
                    emit("phase", name=f"crawling sub-level {current_depth + 1}/{bfs_depth} ({len(current_batch)} pages)")
                    next_level_pages: list[str] = []

                    for i, sub_url in enumerate(current_batch):
                        if len(seen_assets) >= _MAX_ASSETS:
                            break
                        emit("phase", name=f"sub-page [{i+1}/{len(current_batch)}]: {sub_url[:100]}")
                        # Each sub-page gets a 120s budget (Playwright load + asset extraction)
                        try:
                            sub_urls, sub_bodies, sub_subs = await asyncio.wait_for(
                                extract_sub_page_assets(p_context, sub_url),
                                timeout=120,
                            )

                            # Save bodies from this sub-page
                            sub_saved = await _save_playwright_bodies(sub_bodies)
                            if sub_saved > 0:
                                emit("phase", name=f"  → saved {sub_saved} assets from {sub_url[:70]}")

                            # Download non-body assets via httpx
                            for u in sub_urls:
                                if u not in seen_assets:
                                    await try_download(u)

                            # Collect next-level sub-pages (if we need depth 3)
                            if current_depth + 1 < bfs_depth:
                                for su in sub_subs:
                                    if su not in seen_pages and _registered_host(urlparse(su).netloc) == base_host:
                                        seen_pages.add(su)
                                        next_level_pages.append(su)
                        except Exception as e:
                            emit("phase", name=f"  → failed: {e}")

                    current_depth += 1
                    current_batch = next_level_pages

                await browser.close()

        except ImportError:
            emit("phase", name="Playwright not available for sub-pages")
        except Exception as e:
            emit("phase", name=f"Sub-page Playwright failed ({e})")

    # ======================================================================
    # Phase 3: CDN retry via Playwright (full browser context)
    # ======================================================================
    if cdn_failed_urls and types:
        try:
            from .browser import download_assets_via_playwright
            emit("phase", name=f"Retrying {len(cdn_failed_urls)} CDN-blocked assets via Playwright...")
            pw_count = await download_assets_via_playwright(
                urls=cdn_failed_urls,
                dest_dir=save_path,
                file_types=types,
            )
            downloaded += pw_count
            emit("phase", name=f"Playwright downloaded {pw_count} CDN assets")
        except ImportError:
            pass
        except Exception as e:
            emit("phase", name=f"Playwright CDN retry failed ({e})")

    emit("done", downloaded=downloaded, failed=failed)


def _filename_for(resp: httpx.Response) -> str:
    """Derive filename from Content-Disposition, URL path, or content-type."""
    cd = resp.headers.get("content-disposition") or ""
    if "filename=" in cd:
        part = cd.split("filename=", 1)[1].split(";", 1)[0].strip().strip('"')
        if part:
            return _safe(part)
    url = str(resp.url)
    path = urlparse(url).path
    if path and path != "/":
        name = path.rsplit("/", 1)[-1]
        if name:
            name = unquote(name)
            if "." not in name:
                ext = _ct_to_ext(resp.headers.get("content-type", ""))
                if ext:
                    name = f"{name}.{ext}"
            return _safe(name)
    ct = resp.headers.get("content-type", "")
    ext = _ct_to_ext(ct) or "bin"
    from hashlib import md5
    return f"asset-{md5(url.encode()).hexdigest()[:12]}.{ext}"


def _ct_to_ext(content_type: str) -> str:
    ct_map = {
        "image/jpeg": "jpg", "image/png": "png", "image/gif": "gif",
        "image/webp": "webp", "image/svg+xml": "svg", "image/bmp": "bmp",
        "image/tiff": "tiff", "image/avif": "avif", "image/heic": "heic",
        "image/x-icon": "ico", "image/vnd.microsoft.icon": "ico",
        "video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov",
        "video/x-msvideo": "avi", "video/x-matroska": "mkv",
        "application/pdf": "pdf",
        "font/ttf": "ttf", "font/otf": "otf", "font/woff": "woff",
        "font/woff2": "woff2", "application/x-font-ttf": "ttf",
        "application/x-font-otf": "otf", "application/font-woff": "woff",
        "application/font-woff2": "woff2",
    }
    ct = content_type.lower().split(";")[0].strip()
    return ct_map.get(ct, "")


def _safe(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "._-")[:120] or "file"


def _registered_host(netloc: str) -> str:
    host_only = netloc.split(":", 1)[0]
    ext = tldextract.extract(host_only)
    return ext.top_domain_under_public_suffix or host_only


def _same_host(url: str, base: str) -> bool:
    host = urlparse(url).netloc
    if not host:
        return False
    return _registered_host(host) == base
