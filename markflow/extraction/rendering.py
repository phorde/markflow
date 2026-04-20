"""Rendering and HTML safety helpers."""

from __future__ import annotations

import io
import re
from typing import Any


def preprocess_ocr_image(
    image_bytes: bytes,
    *,
    enable_preprocess: bool,
    autocontrast: bool,
    sharpen: bool,
    binarize_threshold: int,
) -> bytes:
    """Apply optional OCR-focused preprocessing and return JPEG bytes."""
    if not enable_preprocess:
        return image_bytes

    try:
        from PIL import Image, ImageFilter, ImageOps  # type: ignore[import-not-found]
    except Exception:
        return image_bytes

    image_obj: Any = Image.open(io.BytesIO(image_bytes))
    if image_obj.mode not in {"L", "RGB"}:
        image_obj = image_obj.convert("L")
    else:
        image_obj = image_obj.convert("L")

    if autocontrast:
        image_obj = ImageOps.autocontrast(image_obj)
    if sharpen:
        image_obj = image_obj.filter(ImageFilter.SHARPEN)
    if 0 < binarize_threshold < 255:
        threshold = int(binarize_threshold)
        lookup_table = [255 if level >= threshold else 0 for level in range(256)]
        image_obj = image_obj.point(lookup_table, mode="1").convert("L")

    output = io.BytesIO()
    image_obj.save(output, format="JPEG", quality=92, optimize=True)
    return output.getvalue()


def sanitize_rendered_html(body: str) -> str:
    """Sanitize rendered HTML fragment to block active content."""
    try:
        import bleach  # type: ignore[import-untyped]
    except Exception:
        sanitized = re.sub(
            r"<script\b[^<]*(?:(?!</script>)<[^<]*)*</script>",
            "",
            body,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            r"\s+on[a-zA-Z]+\s*=\s*(?:\"[^\"]*\"|'[^']*')",
            "",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            r"href\s*=\s*(['\"])javascript:[^'\"]*\1",
            'href="#"',
            sanitized,
            flags=re.IGNORECASE,
        )
        return sanitized

    allowed_tags = [
        "a",
        "blockquote",
        "br",
        "code",
        "em",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "li",
        "ol",
        "p",
        "pre",
        "strong",
        "table",
        "tbody",
        "td",
        "th",
        "thead",
        "tr",
        "ul",
    ]
    allowed_attributes = {
        "a": ["href", "title"],
        "td": ["colspan", "rowspan"],
        "th": ["colspan", "rowspan"],
    }
    allowed_protocols = ["http", "https", "mailto"]
    return bleach.clean(
        body,
        tags=allowed_tags,
        attributes=allowed_attributes,
        protocols=allowed_protocols,
        strip=True,
    )


def render_html_document(markdown_text: str) -> str:
    """Convert markdown into sanitized HTML document."""
    import markdown  # type: ignore[import-untyped]

    body = markdown.markdown(markdown_text, extensions=["tables", "sane_lists"])
    body = sanitize_rendered_html(body)
    return f"""<!DOCTYPE html>
<html lang=\"pt-BR\">
<head>
  <meta charset=\"UTF-8\" />
  <title>Laudo Processado</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 20px; color: #222; line-height: 1.5; }}
    table {{ border-collapse: collapse; width: 100%; table-layout: fixed; margin: 16px 0; }}
    th, td {{ border: 1px solid #ccc; padding: 6px; word-wrap: break-word; }}
    th {{ background: #f0f0f0; }}
  </style>
</head>
<body>{body}</body>
</html>
"""
