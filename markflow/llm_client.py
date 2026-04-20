"""Provider-agnostic OpenAI-compatible client and model discovery helpers."""

from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import aiohttp

from .llm_types import DiscoveredModel, LlmCallResult
from .security import redact_sensitive_text


def normalize_model_identifier(model_id: str) -> str:
    """Normalize model names across providers for matching and scoring."""
    lowered = (model_id or "").strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    lowered = re.sub(r"-+", "-", lowered).strip("-")
    return lowered


def _as_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _redact_sensitive(value: str, api_key: str) -> str:
    """Redact API key and token-like patterns from logs/errors."""
    return redact_sensitive_text(value, secrets=[api_key])


def _validate_secure_base_url(base_url: str) -> None:
    """Allow HTTPS endpoints, or localhost HTTP for local development only."""
    parsed = urlparse(base_url)
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()
    if scheme == "https":
        return
    if scheme == "http" and host in {"localhost", "127.0.0.1", "::1"}:
        return
    raise RuntimeError("insecure_llm_base_url:use_https_or_localhost_http")


class OpenAICompatibleClient:
    """Client for OpenAI-compatible providers with no vendor-specific assumptions."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        provider_name: str = "",
        provider_preset: str = "custom",
        auth_mode: str = "bearer",
        timeout_seconds: int = 20,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or "https://api.openai.com").strip().rstrip("/")
        self.provider_name = (provider_name or "custom-openai-compatible").strip()
        self.provider_preset = (provider_preset or "custom").strip().lower()
        self.auth_mode = (auth_mode or "bearer").strip().lower()
        self.timeout_seconds = max(5, int(timeout_seconds))
        self.extra_headers = dict(extra_headers or {})
        if self.base_url:  # pragma: no branch - constructor always assigns a non-empty default URL
            _validate_secure_base_url(self.base_url)

    @property
    def is_configured(self) -> bool:
        """Return whether required credentials were provided."""
        return bool(self.api_key and self.base_url)

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.auth_mode == "x-api-key":
            headers["x-api-key"] = self.api_key
        else:
            headers["Authorization"] = f"Bearer {self.api_key}"
        headers.update(self.extra_headers)
        return headers

    def _endpoint_candidates(self, suffixes: List[str]) -> List[str]:
        """Build endpoint candidates, avoiding duplicated path segments like /v1/v1."""
        base = self.base_url.rstrip("/")
        base_lower = base.lower()
        candidates: List[str] = []

        for suffix in suffixes:
            normalized_suffix = "/" + suffix.lstrip("/")
            if base_lower.endswith("/v1") and normalized_suffix.startswith("/v1/"):
                normalized_suffix = normalized_suffix[3:]
            if base_lower.endswith("/chat/completions") and normalized_suffix.endswith(
                "/chat/completions"
            ):
                normalized_suffix = ""
            if base_lower.endswith("/models") and normalized_suffix.endswith("/models"):
                normalized_suffix = ""
            url = f"{base}{normalized_suffix}"
            if url not in candidates:
                candidates.append(url)

        return candidates

    async def list_models_async(self, session: aiohttp.ClientSession) -> List[DiscoveredModel]:
        """Discover models using /v1/models and normalize capabilities."""
        if not self.is_configured:
            return []

        payload: Dict[str, Any] = {}
        last_error = ""
        suffixes = ["/v1/models", "/models"]
        if re.search(r"/v\d+$", self.base_url.strip().lower()):
            suffixes = ["/models", "/v1/models"]

        for url in self._endpoint_candidates(suffixes):
            async with session.get(url, headers=self._headers(), allow_redirects=False) as resp:
                if resp.status == 200:
                    payload = await resp.json()
                    break
                detail = await resp.text()
                safe = _redact_sensitive(detail[:220], self.api_key)
                last_error = f"{resp.status}:{url}:{safe}"

        if not payload:
            raise RuntimeError(f"model_discovery_failed:{last_error or 'no_endpoint_available'}")

        models_raw = payload.get("data", []) if isinstance(payload, dict) else []
        discovered: List[DiscoveredModel] = []

        for item in models_raw:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id", "")).strip()
            if not model_id:
                continue

            normalized = normalize_model_identifier(model_id)
            supports_chat = not any(
                token in normalized
                for token in (
                    "embedding",
                    "rerank",
                    "moderation",
                    "audio",
                    "speech",
                    "transcribe",
                    "image-generation",
                )
            )
            supports_vision = any(
                token in normalized
                for token in ("vision", "vl", "omni", "multimodal", "image", "ocr")
            )

            context_window = int(
                item.get("context_window")
                or item.get("max_context_length")
                or item.get("max_input_tokens")
                or 0
            )

            raw_pricing = item.get("pricing")
            pricing: Dict[str, Any] = raw_pricing if isinstance(raw_pricing, dict) else {}
            input_cost = _as_float(
                pricing.get("input")
                or item.get("input_cost_per_million")
                or item.get("prompt_price_per_million")
            )
            output_cost = _as_float(
                pricing.get("output")
                or item.get("output_cost_per_million")
                or item.get("completion_price_per_million")
            )

            discovered.append(
                DiscoveredModel(
                    id=model_id,
                    normalized_id=normalized,
                    supports_chat=supports_chat,
                    supports_vision=supports_vision,
                    context_window=max(0, context_window),
                    input_cost_per_million=input_cost,
                    output_cost_per_million=output_cost,
                    metadata=item,
                )
            )

        return discovered

    async def chat_completion_async(
        self,
        session: aiohttp.ClientSession,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LlmCallResult:
        """Call /v1/chat/completions and normalize text extraction."""
        if not self.is_configured:
            raise RuntimeError("llm_client_not_configured")

        if self.provider_preset == "anthropic":
            return await self._anthropic_messages_async(
                session=session,
                model=model,
                messages=messages,
                max_tokens=max_tokens,
            )

        payload = {
            "model": model,
            "messages": messages,
            "temperature": float(temperature),
            "max_tokens": int(max(1, max_tokens)),
        }

        data: Dict[str, Any] = {}
        last_error = ""
        suffixes = ["/v1/chat/completions", "/chat/completions"]
        if re.search(r"/v\d+$", self.base_url.strip().lower()):
            suffixes = ["/chat/completions", "/v1/chat/completions"]

        for url in self._endpoint_candidates(suffixes):
            async with session.post(
                url, headers=self._headers(), json=payload, allow_redirects=False
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    break
                detail = await resp.text()
                safe = _redact_sensitive(detail[:220], self.api_key)
                last_error = f"{resp.status}:{url}:{safe}"

        if not data:
            raise RuntimeError(f"chat_completion_failed:{last_error or 'no_endpoint_available'}")

        choices = data.get("choices", []) if isinstance(data, dict) else []
        if not choices:
            return LlmCallResult(text="", model=model, usage={})

        message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
        content = message.get("content", "")
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            content = "\n".join(parts)
        if not isinstance(content, str):
            content = str(content)

        return LlmCallResult(
            text=content.strip(),
            model=str(data.get("model") or model),
            usage=data.get("usage", {}) if isinstance(data, dict) else {},
        )

    async def _anthropic_messages_async(
        self,
        session: aiohttp.ClientSession,
        model: str,
        messages: List[Dict[str, Any]],
        max_tokens: int,
    ) -> LlmCallResult:
        """Call Anthropic Messages API and normalize response to common result type."""
        anthropic_messages: List[Dict[str, Any]] = []
        system_parts: List[str] = []

        def _anthropic_content_blocks(content: Any) -> List[Dict[str, Any]]:
            blocks: List[Dict[str, Any]] = []
            if not isinstance(content, list):
                text = str(content).strip()
                return [{"type": "text", "text": text}] if text else []

            for block in content:
                if not isinstance(block, dict):
                    continue
                block_text = block.get("text")
                if isinstance(block_text, str) and block_text.strip():
                    blocks.append({"type": "text", "text": block_text.strip()})
                    continue

                image_url = block.get("image_url")
                if isinstance(image_url, dict):
                    raw_url = str(image_url.get("url", ""))
                else:
                    raw_url = str(image_url or "")
                if not raw_url.startswith("data:") or "," not in raw_url:
                    continue

                header, data = raw_url.split(",", 1)
                media_type = header[5:].split(";", 1)[0] or "image/jpeg"
                blocks.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": data,
                        },
                    }
                )
            return blocks

        for message in messages:
            role = str(message.get("role", "user")).strip().lower()
            content = message.get("content", "")
            content_blocks = _anthropic_content_blocks(content)
            normalized_content = "\n".join(
                str(block.get("text", ""))
                for block in content_blocks
                if block.get("type") == "text"
            ).strip()

            if role == "system":
                if normalized_content:
                    system_parts.append(normalized_content)
                continue

            normalized_role = role if role in {"user", "assistant"} else "user"
            anthropic_messages.append(
                {
                    "role": normalized_role,
                    "content": content_blocks or "[empty]",
                }
            )

        if not anthropic_messages:
            anthropic_messages = [{"role": "user", "content": "Hello."}]

        payload: Dict[str, Any] = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": int(max(1, max_tokens)),
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)

        data: Dict[str, Any] = {}
        last_error = ""
        for url in self._endpoint_candidates(["/v1/messages", "/messages"]):
            async with session.post(
                url, headers=self._headers(), json=payload, allow_redirects=False
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    break
                detail = await resp.text()
                safe = _redact_sensitive(detail[:220], self.api_key)
                last_error = f"{resp.status}:{url}:{safe}"

        if not data:
            raise RuntimeError(f"chat_completion_failed:{last_error or 'no_endpoint_available'}")

        content_blocks = data.get("content", []) if isinstance(data, dict) else []
        text_parts: List[str] = []
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(str(block.get("text", "")))
        text = "\n".join(part for part in text_parts if part).strip()

        return LlmCallResult(
            text=text,
            model=str(data.get("model") or model),
            usage=data.get("usage", {}) if isinstance(data, dict) else {},
        )

    def discover_models_sync(self) -> List[DiscoveredModel]:
        """Sync wrapper for model discovery, used by TUI flows."""

        async def _run() -> List[DiscoveredModel]:
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                return await self.list_models_async(session)

        return asyncio.run(_run())
