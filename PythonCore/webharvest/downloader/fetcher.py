"""Download an asset to a typed subfolder with content-disposition fallback."""
from __future__ import annotations

from hashlib import sha1
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

from ..config import FOLDER_BY_TYPE

_TIMEOUT = 30.0
_MAX_BYTES = 200 * 1024 * 1024  # 200 MB cap to avoid runaway downloads


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
        async with client.stream("GET", url, timeout=_TIMEOUT) as resp:
            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code}"
            total = int(resp.headers.get("content-length", 0))
            if total > _MAX_BYTES:
                return False, f"too large ({total} bytes)"

            name = _filename_for(url, resp.headers.get("content-disposition", ""))
            name = _ensure_ext(name, url, ftype)
            name = _dedupe_name(target_dir, name)
            dest = target_dir / name

            written = 0
            with dest.open("wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                    f.write(chunk)
                    written += len(chunk)
                    if written > _MAX_BYTES:
                        f.close()
                        dest.unlink(missing_ok=True)
                        return False, f"stream exceeded {_MAX_BYTES} bytes"
            return True, str(dest)
    except httpx.TimeoutException:
        return False, "timeout"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def _filename_for(url: str, content_disposition: str) -> str:
    """Pick a filename from Content-Disposition, falling back to URL path."""
    if "filename=" in content_disposition:
        part = content_disposition.split("filename=", 1)[1]
        part = part.split(";", 1)[0].strip().strip('"')
        if part:
            return _safe(part)
    path = urlparse(url).path
    if path and path != "/":
        return _safe(unquote(path.rsplit("/", 1)[-1]) or "index")
    return "index"


def _ensure_ext(name: str, url: str, ftype: str) -> str:
    """If the name lacks an extension, derive one from the URL."""
    if "." in name:
        return name
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
    """If `name` exists, append -1, -2, ... before the extension."""
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
