"""Playwright-powered page loader: executes JS, extracts all asset URLs with browser cookies.
Captures image bodies during page load to bypass CDN anti-hotlink."""
from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright

_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


async def extract_asset_urls(target_url: str) -> tuple[set[str], dict[str, str]]:
    """Load a page in headless Chromium, wait for JS + lazy assets, return (all_urls, cookies_dict)."""
    urls: set[str] = set()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel="chrome", headless=True)
        context = await browser.new_context(
            user_agent=_USER_AGENT,
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()

        # Capture image/media responses
        def _on_resp(resp):
            rt = resp.request.resource_type
            if rt in ("image", "media") and resp.ok:
                if resp.url not in urls:
                    urls.add(resp.url)

        page.on("response", _on_resp)
        page.on("requestfailed", lambda req: urls.add(req.url)
                 if req.resource_type in ("image", "media") else None)

        await page.goto(target_url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)

        # Extract all img/src attributes from DOM
        dom_urls = await page.evaluate("""() => {
            const s = new Set();
            document.querySelectorAll('img[src]').forEach(el => { if (el.src) s.add(el.src); });
            document.querySelectorAll('img[data-src]').forEach(el => { if (el.dataset.src) s.add(el.dataset.src); });
            document.querySelectorAll('img[data-lazy-src]').forEach(el => { if (el.dataset.lazySrc) s.add(el.dataset.lazySrc); });
            document.querySelectorAll('source[srcset]').forEach(el => {
                el.srcset.split(',').forEach(p => {
                    const u = p.trim().split(' ')[0];
                    if (u) s.add(u);
                });
            });
            document.querySelectorAll('source[src]').forEach(el => { if (el.src) s.add(el.src); });
            document.querySelectorAll('video[src]').forEach(el => { if (el.src) s.add(el.src); });
            document.querySelectorAll('video[poster]').forEach(el => { if (el.poster) s.add(el.poster); });
            document.querySelectorAll('a[href]').forEach(el => {
                const h = el.href.toLowerCase();
                if (h.match(/\\.(jpg|jpeg|png|gif|webp|pdf|mp4|mov|bmp|svg|ico)(\\?|$)/)) s.add(el.href);
            });
            document.querySelectorAll('[style]').forEach(el => {
                const bg = el.style.backgroundImage;
                if (bg) {
                    const m = bg.match(/url\\(['"]?([^'")]+)['"]?\\)/);
                    if (m) s.add(m[1]);
                }
            });
            document.querySelectorAll('meta[property],meta[name]').forEach(el => {
                const p = (el.getAttribute('property') || '').toLowerCase();
                const n = (el.getAttribute('name') || '').toLowerCase();
                if (p.includes('image') || n.includes('image')) {
                    const c = el.getAttribute('content');
                    if (c && c.startsWith('http')) s.add(c);
                }
            });
            return Array.from(s);
        }""")

        for u in dom_urls:
            if u and not u.startswith("data:"):
                urls.add(u)

        # Extract cookies
        raw_cookies = await context.cookies()
        cookies: dict[str, str] = {}
        target_domain = urlparse(target_url).netloc.split(":")[0]
        target_domain_lower = target_domain.lower()
        for c in raw_cookies:
            cd = c.get("domain", "").lower()
            if cd and (cd == target_domain_lower or cd.lstrip(".") == target_domain_lower or target_domain_lower.endswith("." + cd.lstrip("."))):
                cookies[c["name"]] = c["value"]

        await browser.close()

    return urls, cookies


async def download_assets_via_playwright(
    urls: list[str],
    dest_dir: str,
    file_types: set[str],
) -> int:
    """Download CDN-protected assets through Playwright's browser session.
    Works where httpx fails (HTTP 567 anti-hotlink) because Chrome has
    the full browser context (cookies, headers, TLS fingerprint)."""
    downloaded = 0
    if not urls:
        return 0

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel="chrome", headless=True)
        context = await browser.new_context(
            user_agent=_USER_AGENT,
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()

        dest = Path(dest_dir)
        for asset_url in urls:
            try:
                resp = await page.goto(asset_url, wait_until="domcontentloaded", timeout=30000)
                if resp and resp.ok:
                    await page.wait_for_timeout(500)
                    body = await page.evaluate("""() => {
                        return new Promise((resolve) => {
                            fetch(document.location.href)
                                .then(r => r.blob())
                                .then(b => {
                                    const reader = new FileReader();
                                    reader.onload = () => resolve(reader.result);
                                    reader.readAsDataURL(b);
                                });
                        });
                    }""")
                    if body and isinstance(body, str) and "," in body:
                        import base64
                        raw = base64.b64decode(body.split(",", 1)[1])
                        ct = body.split(";")[0].split(":")[1] if ":" in body else ""

                        ftype = None
                        if ct.startswith("image/"):
                            ftype = "image"
                        elif ct.startswith("video/"):
                            ftype = "video"

                        if ftype and ftype in file_types:
                            from urllib.parse import urlparse as up
                            path = up(asset_url).path
                            name = path.rsplit("/", 1)[-1] if path else "asset"
                            if "." not in name:
                                ext_map = {"image/jpeg": "jpg", "image/png": "png",
                                           "image/webp": "webp", "image/gif": "gif",
                                           "video/mp4": "mp4"}
                                name = f"{name}.{ext_map.get(ct, 'bin')}"
                            name = "".join(c for c in name if c.isalnum() or c in "._-")[:120] or "file"

                            type_dir_map = {"image": "images", "video": "videos", "pdf": "pdfs"}
                            save_dir = dest / type_dir_map[ftype]
                            save_dir.mkdir(parents=True, exist_ok=True)
                            (save_dir / name).write_bytes(raw)
                            downloaded += 1
                            from ..protocol import emit
                            ct_label = ct.split("/")[-1] if "/" in ct else ct
                            emit("asset.downloaded", type=ftype, path=str(save_dir / name), size=len(raw))
            except Exception:
                pass

        await browser.close()

    return downloaded
