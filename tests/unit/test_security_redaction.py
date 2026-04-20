from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from markflow.security import redact_sensitive_text

pytestmark = pytest.mark.unit


def test_redact_sensitive_text_masks_known_secret_and_bearer() -> None:
    message = "Authorization: Bearer abcdefghijklmnop and key sk-1234567890ABCDEFGH"
    redacted = redact_sensitive_text(message, secrets=["abcdefghijklmnop"])
    assert "abcdefghijklmnop" not in redacted
    assert "Bearer [REDACTED_SECRET]" in redacted
    assert "sk-1234567890ABCDEFGH" not in redacted


@given(
    prefix=st.text(min_size=0, max_size=20),
    suffix=st.text(min_size=0, max_size=20),
)
def test_redaction_property_no_secret_leak(prefix: str, suffix: str) -> None:
    secret = "super-secret-token-value"
    payload = f"{prefix}{secret}{suffix}"
    redacted = redact_sensitive_text(payload, secrets=[secret])
    assert secret not in redacted
