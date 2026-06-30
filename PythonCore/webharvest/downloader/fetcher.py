"""Download an asset to a typed subfolder with content-disposition fallback."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

from ..config import FOLDER_BY_TYPE

_TIMEOUT = 30.0
_MAX_BYTES = 200 * 1024 * 1024  # 200 MB cap


async def download(
    client: httpx.AsyncClient,
    url: str,
    ftype: str,
    save_root: Path,
) -> tuple[bool, str]:
    """Download `url` into `save_root/<ftype>/`. Returns (ok, path_or_error)."""
    target_dir = save_root / FOLDER_BY_TYPE[ftype]
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        resp = await client.get(url, timeout=_TIMEOUT)
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}"

        content_type = resp.headers.get("content-type", "").lower()

        # For images: verify it's actually an image by content-type
        if ftype == "image" and not any(t in content_type for t in ("image/", "octet-stream")):
            return False, f"not an image (content-type: {content_type})"

        # For videos: verify content-type
        if ftype == "video" and not any(t in content_type for t in ("video/", "octet-stream", "mp4")):
            return False, f"not a video (content-type: {content_type})"

        total = len(resp.content)
        if total > _MAX_BYTES:
            return False, f"too large ({total} bytes)"

        name = _filename_for(url, resp.headers.get("content-disposition", ""))
        name = _ensure_ext(name, url, ftype, content_type)
        name = _dedupe_name(target_dir, name)
        dest = target_dir / name

        dest.write_bytes(resp.content)
        return True, str(dest)
    except httpx.TimeoutException:
        return False, "timeout"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _filename_for(url: str, content_disposition: str) -> str:
    if "filename=" in content_disposition:
        part = content_disposition.split("filename=", 1)[1]
        part = part.split(";", 1)[0].strip().strip('"')
        if part:
            return _safe(part)
    path = urlparse(url).path
    if path and path != "/":
        return _safe(unquote(path.rsplit("/", 1)[-1]) or "index")
    return "index"


def _ensure_ext(name: str, url: str, ftype: str, content_type: str) -> str:
    if "." in name:
        return name
    # derive from content-type
    ct_map = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif",
              "image/webp": "webp", "image/svg+xml": "svg", "image/bmp": "bmp",
              "video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov",
              "application/pdf": "pdf"}
    if content_type in ct_map:
        return f"{name}.{ct_map[content_type]}"
    ext = _ext_from_url(url)
    if ext:
        return f"{name}.{ext}"
    default = {"image": "jpg", "video": "mp4", "pdf": "pdf"}[ftype]
    return f"{name}.{default}"


def _ext_from_url(url: str) -> str:
    path = urlparse(url).path.lower()
    if "." in path.rsplit("/", 1)[-1]:
        return path.rsplit(".", 1)[-1].split("?", 1)[0][:8]
    return ""


def _safe(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "._-")[:120] or "file"


def _dedupe_name(dir_: Path, name: str) -> str:
    if not (dir_ / name).exists():
        return name
    stem, _, ext = name.rpartition(".")
    base = stem if ext else name
    suffix = f".{ext}" if ext else ""
    n = 1
    while True:
        candidate = f"{base}-{n}{suffix}"
        if not (dir_ / candidate).exists():
            return candidate
        n += 1
