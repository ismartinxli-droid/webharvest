"""Playwright-powered page loader: executes JS, extracts all asset URLs with browser cookies.
Captures image bodies during page load to bypass CDN anti-hotlink."""
from __future__ import annotations

import asyncio
import json
import base64
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright

_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
_CHROME_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-web-security",
    "--allow-running-insecure-content",
    "--window-size=1920,1080",
]
_INIT_SCRIPT = """
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
"""


def _same_host(url: str, host: str) -> bool:
    h = urlparse(url).netloc.split(":")[0].lower()
    return host == h or h.endswith("." + host) or host.endswith("." + h)


# ---------------------------------------------------------------------------
# High-level API
# ---------------------------------------------------------------------------

async def extract_asset_urls(target_url: str) -> tuple[set[str], dict[str, str], dict[str, bytes], set[str]]:
    """Full extraction with its own Playwright session (seed page)."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel="chrome", headless=True, args=_CHROME_ARGS)
        context = await browser.new_context(
            user_agent=_USER_AGENT, viewport={"width": 1920, "height": 1080},
            locale="zh-CN", timezone_id="Asia/Shanghai",
        )
        page = await context.new_page()
        await page.add_init_script(_INIT_SCRIPT)

        result = await _process_page(context, page, target_url)

        await browser.close()
    return result


# ---------------------------------------------------------------------------
# Internal: shared page processing logic
# ---------------------------------------------------------------------------

async def _process_page(context, page, target_url: str) -> tuple[set[str], dict[str, str], dict[str, bytes], set[str]]:
    """Navigate to target_url and extract every asset URL + saved body.
    Caller manages browser lifecycle; this function only adds data."""
    urls: set[str] = set()
    saved_bodies: dict[str, bytes] = {}

    # --- Response capture ---
    # Collect media (video) URLs during page load. Don't try to capture
    # their bodies here — HTTP 206 partial content responses are unreliable
    # for resp.body(). Instead, collect URLs and download them later via
    # fetch() from the page context, which has full browser session access.
    pending_video_urls: list[str] = []

    async def _on_resp(resp):
        rt = resp.request.resource_type
        if rt in ("image", "font") and resp.ok:
            if resp.url not in urls:
                urls.add(resp.url)
            if resp.url not in saved_bodies:
                try:
                    body = await resp.body()
                    if body and len(body) > 100:
                        saved_bodies[resp.url] = body
                        if resp.url.endswith("@d_progressive"):
                            clean_url = resp.url[:-len("@d_progressive")]
                            if clean_url not in saved_bodies:
                                saved_bodies[clean_url] = body
                except Exception:
                    pass
        elif rt == "media" and resp.ok:
            if resp.url not in urls:
                urls.add(resp.url)
            # Save URL for post-load fetch — don't try resp.body() here
            if resp.url not in pending_video_urls:
                pending_video_urls.append(resp.url)

    page.on("response", _on_resp)
    page.on("requestfailed", lambda req: urls.add(req.url)
             if req.resource_type in ("image", "media", "font") else None)

    # --- Navigate ---
    await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(3000)

    # WAF warmup fallback
    body_snippet = await page.evaluate("() => document.body.innerText.substring(0, 200)")
    if "EdgeOne" in body_snippet or "安全策略拦截" in body_snippet:
        up = urlparse(target_url)
        home_url = f"{up.scheme}://{up.netloc}/"
        if home_url != target_url.rstrip("/") + "/":
            await page.goto(home_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
            await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3000)

    # --- Scroll for lazy-load ---
    h = await page.evaluate("() => document.body.scrollHeight")
    for y in range(0, min(h, 20000), 500):
        await page.evaluate(f"window.scrollTo(0, {y})")
        await page.wait_for_timeout(100)
    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(1500)

    # --- Fonts via stylesheets ---
    font_bodies = await _extract_fonts_from_stylesheets(page)
    for url, body in font_bodies.items():
        saved_bodies[url] = body

    # --- PDFs via fetch ---
    pdf_urls: list[str] = await page.evaluate("""() => {
        const u=[],s=new Set();
        document.querySelectorAll('a[href]').forEach(a=>{
            const h=a.href||'';if(h.includes('.pdf')){
                try{const abs=new URL(h,location.href).href.split('#')[0];if(!s.has(abs)){s.add(abs);u.push(abs);}}catch(e){}
            }
        });
        return u;
    }""")
    if pdf_urls:
        for url, body in (await _download_assets_via_fetch(page, pdf_urls)).items():
            saved_bodies[url] = body

    # --- Videos via fetch() from page context ---
    # Collect video URLs from both DOM and _on_resp, then download all of them
    # via fetch() inside the page context (has full browser session, bypasses WAF).
    dom_video_urls: list[str] = await page.evaluate("""() => {
        const s=new Set();
        document.querySelectorAll('video source[src]').forEach(el=>{if(el.src)s.add(el.src)});
        document.querySelectorAll('video[src]').forEach(el=>{const src=el.getAttribute('src');if(src)s.add(src)});
        return Array.from(s);
    }""")
    all_video_urls = list({u for u in pending_video_urls + dom_video_urls})
    if all_video_urls:
        for url in all_video_urls:
            urls.add(url)
        # Download videos: try all at once with 600s timeout.
        # Per-URL AbortController: 45s. With 14 URLs × 45s worst case = 630s.
        vid_bodies = await _download_assets_via_fetch(page, all_video_urls, timeout=600000)
        for url, body in vid_bodies.items():
            saved_bodies[url] = body

    # --- DOM asset extraction ---
    dom_urls: list[str] = await page.evaluate("""() => {
        const s=new Set();
        const IE=/\\.(jpg|jpeg|png|gif|webp|pdf|mp4|mov|bmp|svg|ico|tiff?)(\\?|$)/i;
        document.querySelectorAll('img[src]').forEach(e=>{if(e.src)s.add(e.src)});
        document.querySelectorAll('img[data-src]').forEach(e=>{if(e.dataset.src)s.add(e.dataset.src)});
        document.querySelectorAll('img[data-lazy-src]').forEach(e=>{if(e.dataset.lazySrc)s.add(e.dataset.lazySrc)});
        document.querySelectorAll('img[data-original]').forEach(e=>{if(e.dataset.original)s.add(e.dataset.original)});
        document.querySelectorAll('source[srcset]').forEach(e=>{e.srcset.split(',').forEach(p=>{const u=p.trim().split(' ')[0];if(u)s.add(u)})});
        document.querySelectorAll('source[src]').forEach(e=>{if(e.src)s.add(e.src)});
        document.querySelectorAll('video[src]').forEach(e=>{if(e.src)s.add(e.src)});
        document.querySelectorAll('video[poster]').forEach(e=>{if(e.poster)s.add(e.poster)});
        document.querySelectorAll('a[href]').forEach(e=>{if(IE.test(e.href))s.add(e.href)});
        document.querySelectorAll('[style]').forEach(e=>{const bg=e.style.backgroundImage;if(bg){const m=bg.match(/url\\(['\"]?([^'\")]+)['\"]?\\)/);if(m)s.add(m[1])}});
        const sb=new Set();
        document.querySelectorAll('div,section,article,header,footer,li,a,span').forEach(e=>{
            try{const bg=getComputedStyle(e).backgroundImage;if(!bg||bg==='none')return;(bg.match(/url\\(["']?([^"')]+)["']?\\)/g)||[]).forEach(m=>{const u=m.replace(/url\\(["']?/,'').replace(/["']?\\)/,'');if(u&&!u.startsWith('data:')&&!sb.has(u)){sb.add(u);s.add(u)}})}catch(e){}
        });
        document.querySelectorAll('meta[property],meta[name]').forEach(e=>{
            const p=(e.getAttribute('property')||'').toLowerCase(),n=(e.getAttribute('name')||'').toLowerCase();
            if(p.includes('image')||n.includes('image')){const c=e.getAttribute('content');if(c&&c.startsWith('http'))s.add(c)}
        });
        document.querySelectorAll('a[href]').forEach(e=>{const h=e.href;if(h&&IE.test(h))s.add(h)});
        return Array.from(s);
    }""")
    for u in dom_urls:
        if u and not u.startswith("data:"):
            urls.add(u)
            if u.endswith("@d_progressive"):
                urls.add(u[:-len("@d_progressive")])

    # --- Cookies ---
    raw_cookies = await context.cookies()
    cookies: dict[str, str] = {}
    target_domain = urlparse(target_url).netloc.split(":")[0].lower()
    for c in raw_cookies:
        cd = c.get("domain", "").lower()
        if cd and (cd == target_domain or cd.lstrip(".") == target_domain or target_domain.endswith("." + cd.lstrip("."))):
            cookies[c["name"]] = c["value"]

    # --- Sub-page links ---
    sub_pages: set[str] = set()
    pw_subpages: list[str] = await page.evaluate("""(host) => {
        const p=[],s=new Set();
        const IX=/\\.(jpg|jpeg|png|gif|webp|bmp|svg|mp4|mov|webm|pdf|ico|avif|tiff|heic|ttf|otf|woff|woff2|eot)(\\?|$)/i;
        document.querySelectorAll('a[href]').forEach(a=>{
            let h=a.getAttribute('href')||'';
            if(!h||h.startsWith('#')||h.startsWith('javascript:')||h.startsWith('mailto:')||h.startsWith('tel:'))return;
            if(h.startsWith('http')&&!h.includes(host))return;
            try{const abs=new URL(h,location.href).href.split('#')[0];if(s.has(abs))return;s.add(abs);if(IX.test(abs))return;if(!abs.startsWith('http'))return;p.push(abs)}catch(e){}
        });
        return p;
    }""", target_domain)
    for u in pw_subpages:
        if _same_host(u, target_domain):
            sub_pages.add(u)

    return urls, cookies, saved_bodies, sub_pages


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _download_assets_via_fetch(page, urls: list[str], timeout: int = 120000) -> dict[str, bytes]:
    """Download assets via fetch() with a per-URL AbortController timeout of 45s.
    Overall evaluate call capped by timeout param."""
    result: dict[str, bytes] = {}
    if not urls:
        return result
    try:
        raw = await asyncio.wait_for(page.evaluate("""(urls) => {
            async function dl(urls){
                const r={};
                for(const u of urls){
                    try{
                        const controller = new AbortController();
                        const tid = setTimeout(() => controller.abort(), 45000);
                        const p = await fetch(u, {credentials:"include", signal: controller.signal});
                        clearTimeout(tid);
                        if(!p.ok){ r[u] = "HTTP:" + p.status; continue; }
                        const b = await p.blob();
                        const reader=new FileReader();
                        const d=await new Promise((res)=>{reader.onload=()=>res(reader.result);reader.readAsDataURL(b)});
                        r[u]=d;
                    }catch(e){ r[u] = "ERR:" + e.message; }
                }
                return JSON.stringify(r);
            }
            return dl(urls);
        }""", urls), timeout=timeout / 1000)  # convert ms to seconds
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
    font_bodies: dict[str, bytes] = {}
    try:
        result = await page.evaluate("""() => {
            const u=[],s=new Set();const FE=['.ttf','.otf','.woff','.woff2','.eot'];
            for(const sh of document.styleSheets){try{for(const r of sh.cssRules||[]){if(!r.cssText.includes('@font-face'))continue;const m=r.cssText.match(/src\\s*:\\s*([^;}]+)/);if(!m)continue;const re=/url\\(["']?([^"')]+)["']?\\)/g;let x;while((x=re.exec(m[1]))!==null){const url=x[1];if(url.startsWith('data:'))continue;if(s.has(url))continue;s.add(url);if(FE.some(e=>url.toLowerCase().includes(e)))u.push(url)}}}catch(e){}}
            return JSON.stringify({urls:u});
        }""")
        data = json.loads(result)
        font_urls = data.get("urls", [])
        if font_urls:
            download_result = await asyncio.wait_for(page.evaluate("""(urls) => {
                async function dl(urls){const r={};for(const u of urls){try{const controller=new AbortController();const tid=setTimeout(()=>controller.abort(),15000);const p=await fetch(u,{credentials:'include',signal:controller.signal});clearTimeout(tid);if(!p.ok)continue;const b=await p.blob();const reader=new FileReader();const d=await new Promise((res)=>{reader.onload=()=>res(reader.result);reader.readAsDataURL(b)});r[u]=d}catch(e){}}return JSON.stringify(r)}
                return dl(urls);
            }""", font_urls), timeout=120)
            raw_results = json.loads(download_result)
            for url, data_url in raw_results.items():
                if isinstance(data_url, str) and "," in data_url:
                    raw = base64.b64decode(data_url.split(",", 1)[1])
                    if raw and len(raw) > 100:
                        font_bodies[url] = raw
    except Exception:
        pass
    return font_bodies


async def download_assets_via_playwright(
    urls: list[str], dest_dir: str, file_types: set[str],
) -> int:
    downloaded = 0
    if not urls:
        return 0
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel="chrome", headless=True, args=_CHROME_ARGS)
        context = await browser.new_context(
            user_agent=_USER_AGENT, viewport={"width": 1920, "height": 1080},
            locale="zh-CN", timezone_id="Asia/Shanghai",
        )
        page = await context.new_page()
        await page.add_init_script(_INIT_SCRIPT)

        dest = Path(dest_dir)
        for asset_url in urls:
            try:
                resp = await page.goto(asset_url, wait_until="domcontentloaded", timeout=30000)
                if resp and resp.ok:
                    await page.wait_for_timeout(500)
                    body = await page.evaluate("""() => {
                        return new Promise((resolve) => {
                            fetch(document.location.href).then(r=>r.blob()).then(b=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.readAsDataURL(b)});
                        });
                    }""")
                    if body and isinstance(body, str) and "," in body:
                        raw = base64.b64decode(body.split(",", 1)[1])
                        ct = body.split(";")[0].split(":")[1] if ":" in body else ""
                        ftype = None
                        if ct.startswith("image/"): ftype = "image"
                        elif ct.startswith("video/"): ftype = "video"
                        elif ct.startswith("font/") or "font" in ct: ftype = "font"
                        if ftype and ftype in file_types:
                            from urllib.parse import urlparse as up
                            path = up(asset_url).path
                            name = path.rsplit("/", 1)[-1] if path else "asset"
                            if "." not in name:
                                ext_map = {"image/jpeg":"jpg","image/png":"png","image/webp":"webp","image/gif":"gif",
                                           "video/mp4":"mp4","font/ttf":"ttf","font/otf":"otf","font/woff":"woff","font/woff2":"woff2"}
                                name = f"{name}.{ext_map.get(ct, 'bin')}"
                            name = "".join(c for c in name if c.isalnum() or c in "._-")[:120] or "file"
                            save_dir = dest / {"image":"images","video":"videos","pdf":"pdfs","font":"fonts"}[ftype]
                            save_dir.mkdir(parents=True, exist_ok=True)
                            (save_dir / name).write_bytes(raw)
                            downloaded += 1
                            from ..protocol import emit
                            emit("asset.downloaded", type=ftype, path=str(save_dir / name), size=len(raw))
            except Exception:
                pass
        await browser.close()
    return downloaded
