"""Playwright-powered page loader: executes JS, extracts all asset URLs with browser cookies.
Captures image bodies during page load to bypass CDN anti-hotlink."""
from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright

_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
# Chrome launch args to avoid WAF detection (e.g. Tencent Cloud EdgeOne)
_CHROME_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-web-security",
    "--allow-running-insecure-content",
    "--window-size=1920,1080",
]


async def extract_asset_urls(target_url: str) -> tuple[set[str], dict[str, str], dict[str, bytes]]:
    """Load a page in headless Chromium, wait for JS + lazy assets, return (all_urls, cookies_dict, saved_bodies).
    saved_bodies contains the raw bytes of font/image/media responses captured during page load,
    which is the only reliable way to get WAF-protected assets (they load fine in Chrome's page context
    but fail with HTTP 567 when httpx or Chrome-in-isolation requests them)."""
    urls: set[str] = set()
    saved_bodies: dict[str, bytes] = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel="chrome", headless=True, args=_CHROME_ARGS)
        context = await browser.new_context(
            user_agent=_USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        page = await context.new_page()

        # Strip webdriver property and spoof browser signals to avoid WAF detection.
        # EdgeOne (Tencent Cloud) checks navigator.webdriver, plugins, languages,
        # hardwareConcurrency, deviceMemory, and permissions.query.
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
            const _origQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (params) => (
                params.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : _origQuery(params)
            );
        """)

        # Capture image/media/font responses AND save their bodies.
        # This is critical: WAF-protected assets (HTTP 567) can only be retrieved
        # during the initial page load when Chrome has the full page context.
        async def _on_resp(resp):
            rt = resp.request.resource_type
            if rt in ("image", "media", "font") and resp.ok:
                if resp.url not in urls:
                    urls.add(resp.url)
                # Save body for CDN/WAF-protected assets
                if resp.url not in saved_bodies:
                    try:
                        body = await resp.body()
                        if body and len(body) > 100:
                            saved_bodies[resp.url] = body
                            # For ampmake CDN: also store under clean URL (without @d_progressive)
                            # so the downloader picks up the original-quality version.
                            if resp.url.endswith("@d_progressive"):
                                clean_url = resp.url[:-len("@d_progressive")]
                                if clean_url not in saved_bodies:
                                    saved_bodies[clean_url] = body
                    except Exception:
                        pass

        page.on("response", _on_resp)
        page.on("requestfailed", lambda req: urls.add(req.url)
                 if req.resource_type in ("image", "media", "font") else None)

        await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3000)  # let initial JS render

        # If the page was blocked by WAF (EdgeOne/CloudFlare), first warm up
        # by visiting the homepage to establish a legitimate browser session,
        # then retry the target page. This is critical for /esg and other
        # sub-paths on nio.cn which have stricter WAF rules than the homepage.
        body_snippet = await page.evaluate("() => document.body.innerText.substring(0, 200)")
        if "EdgeOne" in body_snippet or "安全策略拦截" in body_snippet:
            from urllib.parse import urlparse as _up
            home_url = f"{_up(target_url).scheme}://{_up(target_url).netloc}/"
            if home_url != target_url.rstrip("/") + "/":
                await page.goto(home_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)
                await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(3000)

        # Scroll to trigger lazy-loaded images (many SPAs load images on scroll).
        # lixiang.com and similar sites only render product images when scrolled into view.
        page_height = await page.evaluate("() => document.body.scrollHeight")
        for y in range(0, min(page_height, 20000), 500):
            await page.evaluate(f"window.scrollTo(0, {y})")
            await page.wait_for_timeout(100)
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(1500)  # let scroll-triggered images load

        # Extract @font-face URLs and download fonts via page context.
        # Python Playwright does not fire response events with resource_type="font"
        # for fonts loaded via CSS @font-face (unlike Node.js Playwright which does).
        # We extract URLs from stylesheets directly and download with fetch().
        font_bodies = await _extract_fonts_from_stylesheets(page)
        for url, body in font_bodies.items():
            saved_bodies[url] = body

        # Download linked PDFs via page context (CDN-hosted PDFs are blocked by WAF
        # when fetched via httpx, but work fine with fetch() inside the browser session).
        pdf_urls = await page.evaluate("""() => {
            const urls = [];
            const seen = new Set();
            document.querySelectorAll('a[href]').forEach(a => {
                const href = a.href || a.getAttribute('href') || '';
                if (!href || href.startsWith('javascript:') || href.startsWith('data:')) return;
                const lower = href.toLowerCase();
                if (lower.endsWith('.pdf') || lower.includes('.pdf?')) {
                    try {
                        const abs = new URL(href, location.href).href.split('#')[0];
                        if (!seen.has(abs)) { seen.add(abs); urls.push(abs); }
                    } catch(e) {}
                }
            });
            return urls;
        }""")
        if pdf_urls:
            pdf_bodies = await _download_assets_via_fetch(page, pdf_urls)
            for url, body in pdf_bodies.items():
                saved_bodies[url] = body

        # Extract all img/src attributes from DOM, PLUS computed background images.
        # Many modern sites (e.g. lixiang.com) render car/product photos as CSS
        # background images rather than <img> tags.
        dom_urls = await page.evaluate("""() => {
            const s = new Set();
            const IMG_EXTS = /\\.(jpg|jpeg|png|gif|webp|pdf|mp4|mov|bmp|svg|ico|tiff?)(\\?|$)/i;

            // --- <img> tags ---
            document.querySelectorAll('img[src]').forEach(el => { if (el.src) s.add(el.src); });
            document.querySelectorAll('img[data-src]').forEach(el => { if (el.dataset.src) s.add(el.dataset.src); });
            document.querySelectorAll('img[data-lazy-src]').forEach(el => { if (el.dataset.lazySrc) s.add(el.dataset.lazySrc); });
            document.querySelectorAll('img[data-original]').forEach(el => { if (el.dataset.original) s.add(el.dataset.original); });

            // --- <picture> / <source> ---
            document.querySelectorAll('source[srcset]').forEach(el => {
                el.srcset.split(',').forEach(p => {
                    const u = p.trim().split(' ')[0];
                    if (u) s.add(u);
                });
            });
            document.querySelectorAll('source[src]').forEach(el => { if (el.src) s.add(el.src); });

            // --- <video> ---
            document.querySelectorAll('video[src]').forEach(el => { if (el.src) s.add(el.src); });
            document.querySelectorAll('video[poster]').forEach(el => { if (el.poster) s.add(el.poster); });

            // --- <a href> with image/video extensions ---
            document.querySelectorAll('a[href]').forEach(el => {
                if (IMG_EXTS.test(el.href)) s.add(el.href);
            });

            // --- Inline style background images ---
            document.querySelectorAll('[style]').forEach(el => {
                const bg = el.style.backgroundImage;
                if (bg) {
                    const m = bg.match(/url\\(['"]?([^'")]+)['"]?\\)/);
                    if (m) s.add(m[1]);
                }
            });

            // --- Computed background images (catches CSS class-based backgrounds,
            //     which is how lixiang.com renders all car photos) ---
            const seenBg = new Set();
            document.querySelectorAll('div, section, article, header, footer, li, a, span').forEach(el => {
                try {
                    const bg = getComputedStyle(el).backgroundImage;
                    if (!bg || bg === 'none') return;
                    const matches = bg.match(/url\\(["']?([^"')]+)["']?\\)/g);
                    if (!matches) return;
                    matches.forEach(m => {
                        const url = m.replace(/url\\(["']?/, '').replace(/["']?\\)/, '');
                        if (url && !url.startsWith('data:') && !seenBg.has(url)) {
                            seenBg.add(url);
                            s.add(url);
                        }
                    });
                } catch(e) {}
            });

            // --- <meta> og:image / twitter:image ---
            document.querySelectorAll('meta[property],meta[name]').forEach(el => {
                const p = (el.getAttribute('property') || '').toLowerCase();
                const n = (el.getAttribute('name') || '').toLowerCase();
                if (p.includes('image') || n.includes('image')) {
                    const c = el.getAttribute('content');
                    if (c && c.startsWith('http')) s.add(c);
                }
            });

            // --- <a href> links to downloadable files (PDFs, images, videos)
            //     Many sites host these on CDN domains, not caught by image response hooks.
            document.querySelectorAll('a[href]').forEach(el => {
                const h = el.href;
                if (h && IMG_EXTS.test(h)) s.add(h);
            });

            return Array.from(s);
        }""")

        for u in dom_urls:
            if u and not u.startswith("data:"):
                urls.add(u)
                # For ampmake CDN: if URL has @d_progressive suffix, also add the
                # clean version (without the suffix) to get original-quality image.
                # Example: .../image.jpg@d_progressive → .../image.jpg (original)
                if u.endswith("@d_progressive"):
                    urls.add(u[:-len("@d_progressive")])

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

    return urls, cookies, saved_bodies


async def _download_assets_via_fetch(page, urls: list[str]) -> dict[str, bytes]:
    """Download arbitrary assets via fetch() in the page context.
    Used for CDN-hosted PDFs and other files that WAF blocks for httpx
    but allows inside the browser session."""
    result: dict[str, bytes] = {}
    if not urls:
        return result

    try:
        raw = await page.evaluate("""(urls) => {
            async function dl(urls) {
                const results = {};
                for (const url of urls) {
                    try {
                        const resp = await fetch(url, {credentials: "include"});
                        if (!resp.ok) continue;
                        const blob = await resp.blob();
                        const reader = new FileReader();
                        const base64 = await new Promise((resolve) => {
                            reader.onload = () => resolve(reader.result);
                            reader.readAsDataURL(blob);
                        });
                        results[url] = base64;
                    } catch(e) {}
                }
                return JSON.stringify(results);
            }
            return dl(urls);
        }""", urls)

        import json, base64
        raw_results = json.loads(raw)
        for url, data_url in raw_results.items():
            if isinstance(data_url, str) and "," in data_url:
                raw_bytes = base64.b64decode(data_url.split(",", 1)[1])
                if raw_bytes and len(raw_bytes) > 100:
                    result[url] = raw_bytes
    except Exception:
        pass

    return result


async def _extract_fonts_from_stylesheets(page) -> dict[str, bytes]:
    """Extract @font-face URLs from all accessible stylesheets and download font
    files using fetch() inside the page context (bypasses WAF because it has the
    full browser session with cookies, referer, and TLS fingerprint).

    Returns {url: bytes} dict, same format as saved_bodies."""
    font_bodies: dict[str, bytes] = {}

    try:
        # Step 1: Extract all font URLs from @font-face rules in stylesheets
        result = await page.evaluate("""() => {
            const fontUrls = [];
            const seen = new Set();
            const FONT_EXTS = ['.ttf', '.otf', '.woff', '.woff2', '.eot'];

            for (const sheet of document.styleSheets) {
                try {
                    for (const rule of sheet.cssRules || []) {
                        if (!rule.cssText.includes('@font-face')) continue;
                        // Extract url(...) values from src descriptor
                        const srcMatch = rule.cssText.match(/src\\s*:\\s*([^;}]+)/);
                        if (!srcMatch) continue;
                        const srcValue = srcMatch[1];
                        const urlRe = /url\\(["']?([^"')]+)["']?\\)/g;
                        let m;
                        while ((m = urlRe.exec(srcValue)) !== null) {
                            const url = m[1];
                            // Skip data: URIs
                            if (url.startsWith('data:')) continue;
                            // Skip duplicates
                            if (seen.has(url)) continue;
                            seen.add(url);
                            // Only include actual font files
                            const lower = url.toLowerCase();
                            if (FONT_EXTS.some(ext => lower.includes(ext))) {
                                fontUrls.push(url);
                            }
                        }
                    }
                } catch (e) { /* CORS stylesheet, skip */ }
            }

            // Also scan <link rel="stylesheet"> for font-face in external CSS
            // by checking computed styles (limited but helpful)
            const allElements = document.querySelectorAll('*');
            const fontFamilies = new Set();
            allElements.forEach(el => {
                const ff = getComputedStyle(el).fontFamily;
                if (ff) ff.split(',').forEach(f => fontFamilies.add(f.trim().replace(/['"]/g, '')));
            });

            return JSON.stringify({ urls: fontUrls, families: Array.from(fontFamilies).slice(0, 20) });
        }""")

        import json
        data = json.loads(result)
        font_urls = data.get("urls", [])

        if not font_urls:
            return font_bodies

        # Step 2: Download each font via fetch() in page context
        download_result = await page.evaluate("""(urls) => {
            async function downloadFonts(urls) {
                const results = {};
                for (const url of urls) {
                    try {
                        const resp = await fetch(url, { credentials: 'include' });
                        if (!resp.ok) continue;
                        const blob = await resp.blob();
                        // Convert blob to base64 for transfer back to Python
                        const reader = new FileReader();
                        const base64 = await new Promise((resolve) => {
                            reader.onload = () => resolve(reader.result);
                            reader.readAsDataURL(blob);
                        });
                        results[url] = base64;
                    } catch (e) {
                        // skip failed fonts
                    }
                }
                return JSON.stringify(results);
            }
            return downloadFonts(urls);
        }""", font_urls)

        raw_results = json.loads(download_result)
        import base64
        for url, data_url in raw_results.items():
            if isinstance(data_url, str) and "," in data_url:
                raw = base64.b64decode(data_url.split(",", 1)[1])
                if raw and len(raw) > 100:
                    font_bodies[url] = raw

    except Exception:
        pass

    return font_bodies


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
        browser = await pw.chromium.launch(channel="chrome", headless=True, args=_CHROME_ARGS)
        context = await browser.new_context(
            user_agent=_USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        page = await context.new_page()

        # Strip webdriver property
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
        """)

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
                        elif ct.startswith("font/") or "font" in ct:
                            ftype = "font"

                        if ftype and ftype in file_types:
                            from urllib.parse import urlparse as up
                            path = up(asset_url).path
                            name = path.rsplit("/", 1)[-1] if path else "asset"
                            if "." not in name:
                                ext_map = {"image/jpeg": "jpg", "image/png": "png",
                                           "image/webp": "webp", "image/gif": "gif",
                                           "video/mp4": "mp4",
                                           "font/ttf": "ttf", "font/otf": "otf",
                                           "font/woff": "woff", "font/woff2": "woff2"}
                                name = f"{name}.{ext_map.get(ct, 'bin')}"
                            name = "".join(c for c in name if c.isalnum() or c in "._-")[:120] or "file"

                            type_dir_map = {"image": "images", "video": "videos", "pdf": "pdfs", "font": "fonts"}
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
