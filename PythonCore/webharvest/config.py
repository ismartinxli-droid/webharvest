"""Static configuration: file-type extension sets and folder mapping."""
from __future__ import annotations

IMAGE_EXTS: set[str] = {
    "jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "tiff", "avif", "heic",
}
VIDEO_EXTS: set[str] = {
    "mp4", "mov", "webm", "mkv", "avi", "m4v", "flv",
}
PDF_EXTS: set[str] = {"pdf"}
FONT_EXTS: set[str] = {"ttf", "otf", "woff", "woff2", "eot"}

FOLDER_BY_TYPE: dict[str, str] = {
    "image": "images",
    "video": "videos",
    "pdf": "pdfs",
    "font": "fonts",
}
