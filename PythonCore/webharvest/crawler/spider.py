"""BFS site crawler: discovers pages, extracts ALL URLs, downloads by content-type.
Uses Playwright for JS rendering when available, falls back to static HTML parsing."""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote

import httpx
import tldextract
from selectolax.parser import HTMLParser

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


async def run(url: str, types: set[str], save_path: str, max_depth: int = 3) -> None:
    """Crawl pages up to max_depth levels, download all matching assets.

    Depth semantics (user-visible):
      depth=1 → seed page only (no sub-page crawling)
      depth=2 → seed + sub-pages (links from seed page)
      depth=3 → seed + sub-pages + sub-sub-pages
      (capped at 3 for performance)
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
    user_depth = max_depth
    bfs_depth = max(0, user_depth - 1)

    emit("phase", name=f"crawling (seed + {bfs_depth} sub-level{'s' if bfs_depth != 1 else ''})")
    frontier = UrlFrontier(seed=url)
    seen_pages: set[str] = {url}
    seen_assets: set[str] = set()
    downloaded = 0
    failed = 0
    cdn_failed_urls: list[str] = []  # URLs that failed with HTTP 567 (CDN anti-hotlink)
    sem = asyncio.Semaphore(_MAX_CONCURRENT)

    # Try to use Playwright for JS rendering; fall back to static HTML
    # NOTE: browser_urls must NOT be added to seen_assets here — try_download()
    # checks seen_assets to decide whether to download. If we pre-populate it,
    # Playwright-discovered assets will be silently skipped.
    browser_urls: set[str] = set()
    browser_cookies: dict[str, str] = {}
    saved_bodies: dict[str, bytes] = {}  # bodies captured during Playwright page load
    pw_sub_pages: set[str] = set()  # sub-page links from Playwright-rendered DOM
    try:
        from .browser import extract_asset_urls as browser_extract

        emit("phase", name="launching Chromium...")
        browser_urls, browser_cookies, saved_bodies, pw_sub_pages = await browser_extract(url)
        emit("phase", name=f"Chromium found {len(browser_urls)} resources")
    except ImportError:
        emit("phase", name="Playwright not available, using static parser")
    except Exception as e:
        emit("phase", name=f"Playwright failed ({e}), using static parser")

    # Build httpx client with cookies from Playwright session
    # Use the seed URL as Referer for CDN anti-hotlink bypass
    client_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": url.rstrip("/") + "/",
    }
    cookie_domain = parsed.netloc.split(":")[0]
    if browser_cookies:
        client_cookies = httpx.Cookies()
        for name, value in browser_cookies.items():
            client_cookies.set(name, value, domain=cookie_domain)

    async with httpx.AsyncClient(
        timeout=_REQUEST_TIMEOUT,
        follow_redirects=True,
        headers=client_headers,
        cookies=client_cookies if browser_cookies else None,
    ) as client:

        async def try_download(asset_url: str) -> None:
            """Try to download a URL. If it matches a wanted content-type, save it."""
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
                    # Collect CDN anti-hotlink failures for Playwright retry
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

                ftype: str | None = None
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
                return

        async def process_page(page_url: str, depth: int) -> None:
            nonlocal downloaded, failed
            try:
                async with sem:
                    resp = await client.get(page_url)
                if resp.status_code != 200:
                    return
                ct = (resp.headers.get("content-type") or "").lower()
                if not ct.startswith("text/html") and "html" not in ct:
                    return
            except Exception:
                return

            # Detect WAF block pages (EdgeOne / CloudFlare) and skip quickly
            page_text = resp.text
            if len(page_text) < 500 or "EdgeOne" in page_text or "安全策略拦截" in page_text or "cf-browser-verification" in page_text:
                return

            html = HTMLParser(page_text)

            # Extract ALL URLs from the page for asset checking
            all_urls: set[str] = set()

            # 1. All src/srcset/data-src attributes (images, videos, sources)
            for attr in ("src", "data-src", "data-original", "data-lazy-src",
                         "data-srcset", "data-flickity-lazyload"):
                for el in html.css(f"[{attr}]"):
                    val = el.attributes.get(attr) or ""
                    if attr == "data-srcset" or attr == "srcset":
                        for part in val.split(","):
                            url_part = part.strip().split(" ")[0]
                            if url_part:
                                all_urls.add(urljoin(page_url, url_part))
                    else:
                        if val and not val.startswith("data:"):
                            all_urls.add(urljoin(page_url, val))

            # 2. All href attributes (potential PDF links, or redirects to images)
            for a in html.css("a[href]"):
                href = a.attributes.get("href") or ""
                if href and not href.startswith(("#", "javascript:", "mailto:", "tel:")):
                    # Only add if it looks like a file (has extension or common patterns)
                    path_lower = href.lower()
                    if any(ext in path_lower for ext in (".jpg", ".jpeg", ".png", ".gif",
                                                          ".webp", ".bmp", ".svg", ".mp4",
                                                          ".mov", ".pdf", ".webm", ".ico",
                                                          ".avif", ".tiff", ".heic")):
                        all_urls.add(urljoin(page_url, href.split("#")[0]))

            # 3. Meta tags (og:image etc)
            for meta in html.css("meta[property], meta[name]"):
                prop = (meta.attributes.get("property") or "").lower()
                name = (meta.attributes.get("name") or "").lower()
                if "image" in prop or "image" in name:
                    content = meta.attributes.get("content") or ""
                    if content and content.startswith("http"):
                        all_urls.add(content)

            # 4. Link tags (favicon, preload images etc)
            for link in html.css("link[href]"):
                href = link.attributes.get("href") or ""
                rel = (link.attributes.get("rel") or "").lower()
                if href and ("icon" in rel or "image" in rel or "preload" in rel):
                    if not href.startswith("data:"):
                        all_urls.add(urljoin(page_url, href))

            # 5. CSS background-image in style attribute (hero/banner images)
            _CSS_URL_RE = re.compile(r"url\(['\"]?(.*?)['\"]?\)")
            for el in html.css("[style]"):
                style_val = el.attributes.get("style") or ""
                if "background" in style_val.lower():
                    for match in _CSS_URL_RE.finditer(style_val):
                        css_url = match.group(1)
                        if css_url and not css_url.startswith("data:"):
                            all_urls.add(urljoin(page_url, css_url))

            # 6. More data-* attributes for lazy-loaded backgrounds
            for attr in ("data-bg", "data-background", "data-background-image",
                         "data-lazy", "data-echo", "data-lazyload", "data-src-url"):
                for el in html.css(f"[{attr}]"):
                    val = el.attributes.get(attr) or ""
                    if val and not val.startswith("data:") and "{" not in val:
                        all_urls.add(urljoin(page_url, val))

            # 7. Picture > source srcset
            for source in html.css("picture source[srcset]"):
                srcset = source.attributes.get("srcset") or ""
                for part in srcset.split(","):
                    url_part = part.strip().split(" ")[0]
                    if url_part:
                        all_urls.add(urljoin(page_url, url_part))
            for source in html.css("picture source[src]"):
                src = source.attributes.get("src") or ""
                if src and not src.startswith("data:"):
                    all_urls.add(urljoin(page_url, src))

            # 8. Parse <style> tag content for CSS background-image rules
            for style_tag in html.css("style"):
                css_text = style_tag.text() or ""
                if "background" in css_text:
                    for match in _CSS_URL_RE.finditer(css_text):
                        css_url = match.group(1)
                        if css_url and not css_url.startswith("data:"):
                            full_url = urljoin(page_url, css_url)
                            # Only add same-host background images
                            if _same_host(full_url, base_host):
                                all_urls.add(full_url)
            # Also parse inline CSS in <div style="..."> etc — already done in #5

            # 9. External CSS files (link rel="stylesheet")
            #    Download CSS and extract background-image URLs.
            for link in html.css("link[rel='stylesheet']"):
                css_url = link.attributes.get("href") or ""
                if css_url and not css_url.startswith("data:"):
                    full_css_url = urljoin(page_url, css_url)
                    if _same_host(full_css_url, base_host):
                        try:
                            async with sem:
                                css_resp = await client.get(full_css_url, timeout=10)
                            if css_resp.status_code == 200:
                                css_text = css_resp.text
                                for match in _CSS_URL_RE.finditer(css_text):
                                    img_url = match.group(1)
                                    if img_url and not img_url.startswith("data:"):
                                        all_urls.add(urljoin(full_css_url, img_url))
                        except Exception:
                            pass

            # Download asset URLs discovered on this page.
            # Asset URLs (with known file extensions) are downloaded regardless of host —
            # many sites host PDFs/images on CDN domains (e.g. cdn-public.nio.com).
            # Only page-discovered links need same-host filtering.
            _ASSET_EXT_RE = re.compile(
                r"\.(jpg|jpeg|png|gif|webp|bmp|svg|mp4|mov|webm|pdf|ico|avif|tiff|heic|ttf|otf|woff|woff2)(\?.*)?$",
                re.IGNORECASE,
            )
            for asset_url in all_urls:
                if _ASSET_EXT_RE.search(asset_url):
                    await try_download(asset_url)

            # Discover new page links (sub-pages) — only if not at max depth
            if depth < bfs_depth:
                for a in html.css("a[href]"):
                    href = a.attributes.get("href") or ""
                    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                        continue
                    abs_url = urljoin(page_url, href.split("#")[0])
                    if _same_host(abs_url, base_host) and abs_url not in seen_pages:
                        seen_pages.add(abs_url)
                        frontier.push(abs_url)

            emit("pages.crawled", count=len(seen_pages))

        # First, save all assets captured during Playwright page load.
        # These bodies were downloaded by Chrome with full page context (cookies, referer, JS)
        # and cannot be fetched by httpx (WAF blocks with HTTP 567).
        pw_saved = 0
        if saved_bodies:
            emit("phase", name=f"Saving {len(saved_bodies)} Playwright-captured asset bodies...")
            for asset_url, body in saved_bodies.items():
                if asset_url in seen_assets:
                    continue
                seen_assets.add(asset_url)
                # Determine content-type and type from response headers
                # We don't have headers, so use URL extension as fallback
                from ..config import FOLDER_BY_TYPE, IMAGE_EXTS, VIDEO_EXTS, FONT_EXTS, PDF_EXTS
                url_lower = asset_url.lower()
                ftype = None
                for ext in IMAGE_EXTS:
                    if f".{ext}" in url_lower or f".{ext}?" in url_lower:
                        ftype = "image"
                        break
                if ftype is None:
                    for ext in VIDEO_EXTS:
                        if f".{ext}" in url_lower or f".{ext}?" in url_lower:
                            ftype = "video"
                            break
                if ftype is None:
                    for ext in FONT_EXTS:
                        if f".{ext}" in url_lower or f".{ext}?" in url_lower:
                            ftype = "font"
                            break
                if ftype is None:
                    for ext in PDF_EXTS:
                        if f".{ext}" in url_lower or f".{ext}?" in url_lower:
                            ftype = "pdf"
                            break
                if ftype is None or ftype not in types:
                    continue
                # Derive filename from URL
                path_part = urlparse(asset_url).path
                name = path_part.rsplit("/", 1)[-1] if "/" in path_part else "asset"
                name = unquote(name)
                name = _safe(name)
                dest_dir = Path(save_path) / FOLDER_BY_TYPE[ftype]
                dest_dir.mkdir(parents=True, exist_ok=True)
                (dest_dir / name).write_bytes(body)
                pw_saved += 1
                downloaded += 1
                emit("asset.downloaded", type=ftype, path=str(dest_dir / name), size=len(body))
            emit("phase", name=f"Playwright captured {pw_saved} assets directly")

        # Push sub-page links discovered by Playwright into the frontier.
        # These are real same-host page URLs extracted from the rendered DOM.
        # httpx-based process_page would fail on WAF-protected sites, so we
        # must use Playwright-discovered links for depth crawling.
        depth1_pages = []
        for sub_url in pw_sub_pages:
            if sub_url not in seen_pages:
                seen_pages.add(sub_url)
                frontier.push(sub_url)
                depth1_pages.append(sub_url)
        if depth1_pages:
            emit("phase", name=f"Playwright found {len(depth1_pages)} sub-page links")

        # Next, download Playwright-discovered assets via httpx (non-WAF ones).
        # Playwright-captured bodies are already saved and added to seen_assets,
        # so try_download will skip them.
        remaining_urls = [u for u in browser_urls if u not in seen_assets]
        if remaining_urls:
            emit("phase", name=f"Downloading {len(remaining_urls)} remaining assets via HTTP...")
            for asset_url in remaining_urls:
                await try_download(asset_url)

        # BFS layer by layer.
        # Seed was pushed by UrlFrontier. Drain it — it's already processed by Playwright.
        # Sub-pages from Playwright DOM are in the frontier and will be processed by BFS.
        frontier.pop_batch(1)
        current_depth = 0
        while not frontier.empty() and len(seen_pages) < _MAX_PAGES and current_depth < bfs_depth:
            batch = frontier.pop_batch(8)
            emit("phase", name=f"crawling sub-level {current_depth + 1}/{bfs_depth} ({len(batch)} pages)")
            await asyncio.gather(*(process_page(u, current_depth) for u in batch))
            current_depth += 1

    # Retry CDN-failed assets via Playwright (full browser environment bypasses anti-hotlink)
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
                # Add extension from content-type
                ext = _ct_to_ext(resp.headers.get("content-type", ""))
                if ext:
                    name = f"{name}.{ext}"
            return _safe(name)

    # Fallback: hash-based name
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
