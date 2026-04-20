from __future__ import annotations

import asyncio

import pytest

from markflow.llm_client import OpenAICompatibleClient

pytestmark = pytest.mark.unit


class _FakeResponse:
    def __init__(self, status: int, payload: dict | None = None, text: str = "") -> None:
        self.status = status
        self._payload = payload or {}
        self._text = text

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def json(self) -> dict:
        return self._payload

    async def text(self) -> str:
        return self._text


class _FakeSession:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self.responses = list(responses)

    def get(self, *args, **kwargs):
        return self.responses.pop(0)

    def post(self, *args, **kwargs):
        return self.responses.pop(0)


def test_list_models_raises_with_non_200_response() -> None:
    client = OpenAICompatibleClient(api_key="key", base_url="https://api.example.com/v1")
    session = _FakeSession([_FakeResponse(401, text="unauthorized")])
    with pytest.raises(RuntimeError):
        asyncio.run(client.list_models_async(session))  # type: ignore[arg-type]


def test_chat_completion_raises_with_non_200_response() -> None:
    client = OpenAICompatibleClient(api_key="key", base_url="https://api.example.com/v1")
    session = _FakeSession([_FakeResponse(500, text="server fail")])
    with pytest.raises(RuntimeError):
        asyncio.run(
            client.chat_completion_async(
                session,  # type: ignore[arg-type]
                model="gpt-x",
                messages=[{"role": "user", "content": "hello"}],
            )
        )


def test_anthropic_messages_path_returns_text() -> None:
    client = OpenAICompatibleClient(
        api_key="key",
        base_url="https://api.anthropic.com",
        provider_preset="anthropic",
        auth_mode="x-api-key",
    )
    session = _FakeSession(
        [
            _FakeResponse(
                200,
                payload={
                    "model": "claude-3",
                    "content": [{"type": "text", "text": "ok"}],
                    "usage": {"input_tokens": 1},
                },
            )
        ]
    )
    result = asyncio.run(
        client.chat_completion_async(
            session,  # type: ignore[arg-type]
            model="claude-3",
            messages=[{"role": "user", "content": "hi"}],
        )
    )
    assert result.text == "ok"
