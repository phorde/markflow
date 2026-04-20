"""Cache key/path helpers for extraction artifacts."""

from __future__ import annotations

import time
from pathlib import Path


def page_cache_path(cache_dir: Path, kind: str, page_index: int, payload_signature: str) -> Path:
    return cache_dir / f"{page_index + 1:04d}.{kind}.{payload_signature}.txt"


def rendered_cache_path(cache_dir: Path, page_index: int, payload_signature: str) -> Path:
    return cache_dir / f"{page_index + 1:04d}.render.{payload_signature}.b64"


def render_profile_payload(
    doc_fingerprint: str,
    zoom_matrix: float,
    max_image_side_px: int,
    grayscale: bool,
    preprocess_enabled: bool,
    autocontrast: bool,
    sharpen: bool,
    binarize_threshold: int,
    schema_version: int = 1,
) -> str:
    return (
        f"v{int(schema_version)}:{doc_fingerprint}:{zoom_matrix:.3f}:{max_image_side_px}:"
        f"{int(grayscale)}:{int(preprocess_enabled)}:{int(autocontrast)}:"
        f"{int(sharpen)}:{binarize_threshold}"
    )


def is_cache_entry_valid(path: Path, ttl_seconds: int, now: float | None = None) -> bool:
    """Return whether a cache file can be reused under TTL constraints."""
    if not path.exists() or not path.is_file():
        return False
    ttl = int(ttl_seconds)
    if ttl <= 0:
        return True
    reference_now = time.time() if now is None else float(now)
    age_seconds = max(0.0, reference_now - path.stat().st_mtime)
    return age_seconds <= ttl
