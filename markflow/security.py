"""Security helpers for secret redaction and safe reporting."""

from __future__ import annotations

import re
from typing import Iterable


def redact_sensitive_text(value: str, secrets: Iterable[str] | None = None) -> str:
    text = value or ""
    for secret in secrets or []:
        token = (secret or "").strip()
        if token:
            text = text.replace(token, "[REDACTED_SECRET]")

    patterns = [
        (r"Bearer\s+[A-Za-z0-9._\-]{10,}", "Bearer [REDACTED_TOKEN]"),
        (r"\bsk-[A-Za-z0-9]{16,}\b", "[REDACTED_API_KEY]"),
        (r"\b[A-Za-z0-9_\-]{24,}\b", "[REDACTED_LONG_TOKEN]"),
    ]
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)
    return text
