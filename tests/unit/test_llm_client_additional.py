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
    def __init__(self, get_responses=None, post_responses=None) -> None:
        self.get_responses = list(get_responses or [])
        self.post_responses = list(post_responses or [])
        self.post_payloads: list[dict] = []

    def get(self, *args, **kwargs):
        return self.get_responses.pop(0)

    def post(self, *args, **kwargs):
        self.post_payloads.append(kwargs.get("json", {}))
        return self.post_responses.pop(0)


def test_list_models_marks_non_chat_models() -> None:
    client = OpenAICompatibleClient(api_key="k", base_url="https://api.example.com/v1")
    session = _FakeSession(
        get_responses=[
            _FakeResponse(
                200,
                payload={
                    "data": [
                        {"id": "embedding-large", "context_window": 8000},
                        {"id": "vision-ocr-pro", "context_window": 128000},
                    ]
                },
            )
        ]
    )
    models = asyncio.run(client.list_models_async(session))  # type: ignore[arg-type]
    assert len(models) == 2
    assert models[0].supports_chat is False
    assert models[1].supports_vision is True


def test_chat_completion_handles_list_content_response() -> None:
    client = OpenAICompatibleClient(api_key="k", base_url="https://api.example.com/v1")
    session = _FakeSession(
        post_responses=[
            _FakeResponse(
                200,
                payload={
                    "model": "x",
                    "choices": [
                        {
                            "message": {
                                "content": [
                                    {"type": "output_text", "text": "a"},
                                    {"type": "output_text", "text": "b"},
                                ]
                            }
                        }
                    ],
                },
            )
        ]
    )
    result = asyncio.run(
        client.chat_completion_async(
            session,  # type: ignore[arg-type]
            model="x",
            messages=[{"role": "user", "content": "hi"}],
        )
    )
    assert result.text == "a\nb"


def test_anthropic_messages_with_system_and_block_content() -> None:
    client = OpenAICompatibleClient(
        api_key="k",
        base_url="https://api.anthropic.com",
        provider_preset="anthropic",
        auth_mode="x-api-key",
    )
    session = _FakeSession(
        post_responses=[
            _FakeResponse(
                200,
                payload={
                    "model": "claude",
                    "content": [{"type": "text", "text": "done"}],
                    "usage": {"input_tokens": 1},
                },
            )
        ]
    )
    result = asyncio.run(
        client.chat_completion_async(
            session,  # type: ignore[arg-type]
            model="claude",
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": [{"type": "text", "text": "hello"}]},
            ],
        )
    )
    assert result.text == "done"
    assert session.post_payloads[0]["system"] == "sys"


def test_anthropic_messages_preserves_data_uri_images() -> None:
    client = OpenAICompatibleClient(
        api_key="k",
        base_url="https://api.anthropic.com",
        provider_preset="anthropic",
        auth_mode="x-api-key",
    )
    session = _FakeSession(
        post_responses=[
            _FakeResponse(
                200,
                payload={"model": "claude", "content": [{"type": "text", "text": "done"}]},
            )
        ]
    )
    result = asyncio.run(
        client.chat_completion_async(
            session,  # type: ignore[arg-type]
            model="claude",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "read this"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64,aW1hZ2U="},
                        },
                    ],
                }
            ],
        )
    )

    content = session.post_payloads[0]["messages"][0]["content"]
    assert result.text == "done"
    assert content[0] == {"type": "text", "text": "read this"}
    assert content[1]["type"] == "image"
    assert content[1]["source"] == {
        "type": "base64",
        "media_type": "image/png",
        "data": "aW1hZ2U=",
    }
