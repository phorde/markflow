"""Known provider presets with official auth/key conventions.

The presets align with provider documentation for API key usage and base URLs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class ProviderPreset:
    """Provider preset with official auth and endpoint defaults."""

    key: str
    label: str
    base_url: str
    api_key_env_var: str
    auth_mode: str
    required_headers: Dict[str, str]


_PRESETS: Dict[str, ProviderPreset] = {
    "custom": ProviderPreset(
        "custom",
        "Custom (manual URL)",
        "",
        "LLM_API_KEY",
        "bearer",
        {},
    ),
    "openai": ProviderPreset(
        "openai",
        "OpenAI",
        "https://api.openai.com/v1",
        "OPENAI_API_KEY",
        "bearer",
        {},
    ),
    "anthropic": ProviderPreset(
        "anthropic",
        "Anthropic",
        "https://api.anthropic.com",
        "ANTHROPIC_API_KEY",
        "x-api-key",
        {"anthropic-version": "2023-06-01"},
    ),
    "gemini": ProviderPreset(
        "gemini",
        "Google Gemini (OpenAI-compatible)",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "GEMINI_API_KEY",
        "bearer",
        {},
    ),
    "openrouter": ProviderPreset(
        "openrouter",
        "OpenRouter",
        "https://openrouter.ai/api/v1",
        "OPENROUTER_API_KEY",
        "bearer",
        {
            "HTTP-Referer": "https://localhost",
            "X-OpenRouter-Title": "ExtratorLaudos",
        },
    ),
    "z-ai": ProviderPreset(
        "z-ai",
        "Z.AI",
        "https://api.z.ai/api/paas/v4",
        "ZAI_API_KEY",
        "bearer",
        {},
    ),
}


def list_provider_preset_keys() -> List[str]:
    """Return provider preset keys in stable UI/CLI order."""
    return ["custom", "openai", "anthropic", "gemini", "openrouter", "z-ai"]


def get_provider_label(key: str) -> str:
    """Return user-facing label for a provider preset key."""
    preset = _PRESETS.get((key or "").strip().lower(), _PRESETS["custom"])
    return preset.label


def get_provider_preset(key: str) -> ProviderPreset:
    """Return full provider preset metadata by key."""
    return _PRESETS.get((key or "").strip().lower(), _PRESETS["custom"])


def get_provider_api_key_env_var(key: str) -> str:
    """Return official environment variable name for provider API key."""
    return get_provider_preset(key).api_key_env_var


def resolve_provider_base_url(provider_preset: str, zai_plan: str) -> str:
    """Resolve base URL for provider preset and optional Z.AI plan selection."""
    key = (provider_preset or "custom").strip().lower()
    plan = (zai_plan or "general").strip().lower()

    if key == "z-ai":
        if plan == "coding":
            return "https://api.z.ai/api/coding/paas/v4"
        return "https://api.z.ai/api/paas/v4"

    return _PRESETS.get(key, _PRESETS["custom"]).base_url


def apply_provider_preset(
    provider_preset: str,
    zai_plan: str,
    current_base_url: str,
    current_provider_name: str,
) -> Tuple[str, str]:
    """Apply provider preset defaults to base URL/provider name when suitable."""
    key = (provider_preset or "custom").strip().lower()
    resolved_base = resolve_provider_base_url(key, zai_plan)
    base_url = (current_base_url or "").strip() or resolved_base
    provider_name = (current_provider_name or "").strip() or get_provider_label(key)
    return base_url, provider_name
