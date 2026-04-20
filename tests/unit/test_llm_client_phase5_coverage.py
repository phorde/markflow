from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from markflow.llm_client import OpenAICompatibleClient, _as_float, _validate_secure_base_url

pytestmark = pytest.mark.unit


class _Response:
    def __init__(self, status: int, payload: object | None = None, text: str = "") -> None:
        self.status = status
        self._payload = payload
        self._text = text

    async def __aenter__(self) -> "_Response":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def json(self) -> object:
        return self._payload

    async def text(self) -> str:
        return self._text


class _Session:
    def __init__(self, *, get_responses=None, post_responses=None) -> None:
        self.get_responses = list(get_responses or [])
        self.post_responses = list(post_responses or [])
        self.get_urls: list[str] = []
        self.post_urls: list[str] = []
        self.post_payloads: list[dict] = []

    def get(self, url: str, **kwargs: object) -> _Response:
        self.get_urls.append(url)
        return self.get_responses.pop(0)

    def post(self, url: str, **kwargs: object) -> _Response:
        self.post_urls.append(url)
        self.post_payloads.append(kwargs.get("json", {}))  # type: ignore[arg-type]
        return self.post_responses.pop(0)


def test_private_float_and_url_validation_edges() -> None:
    assert _as_float("bad") is None
    assert _as_float(None) is None
    _validate_secure_base_url("http://localhost:8000")
    _validate_secure_base_url("http://127.0.0.1:8000")
    _validate_secure_base_url("http://[::1]:8000")
    with pytest.raises(RuntimeError):
        _validate_secure_base_url("http://remote.example.com")


def test_endpoint_candidates_deduplicate_terminal_paths() -> None:
    chat_client = OpenAICompatibleClient(
        api_key="k",
        base_url="https://api.example.com/v1/chat/completions",
    )
    assert chat_client._endpoint_candidates(["/v1/chat/completions", "/chat/completions"]) == [
        "https://api.example.com/v1/chat/completions"
    ]

    models_client = OpenAICompatibleClient(api_key="k", base_url="https://api.example.com/models")
    assert models_client._endpoint_candidates(["/v1/models", "/models"]) == [
        "https://api.example.com/models"
    ]


def test_list_models_unconfigured_and_payload_filtering() -> None:
    client = OpenAICompatibleClient(api_key="", base_url="https://api.example.com")
    assert asyncio.run(client.list_models_async(_Session())) == []  # type: ignore[arg-type]

    configured = OpenAICompatibleClient(api_key="k", base_url="https://api.example.com")
    session = _Session(
        get_responses=[
            _Response(
                200,
                payload={
                    "data": [
                        "bad",
                        {"id": ""},
                        {
                            "id": "omni-image-generation",
                            "max_context_length": -10,
                            "pricing": {"input": "bad", "output": "2.5"},
                        },
                        {
                            "id": "chat-model",
                            "max_input_tokens": 32000,
                            "prompt_price_per_million": "1.5",
                            "completion_price_per_million": "2.5",
                        },
                    ]
                },
            )
        ]
    )
    models = asyncio.run(configured.list_models_async(session))  # type: ignore[arg-type]
    assert [model.id for model in models] == ["omni-image-generation", "chat-model"]
    assert models[0].supports_chat is False
    assert models[0].supports_vision is True
    assert models[0].context_window == 0
    assert models[0].input_cost_per_million is None
    assert models[0].output_cost_per_million == 2.5
    assert models[1].context_window == 32000


def test_list_models_non_dict_payload_returns_empty_list() -> None:
    client = OpenAICompatibleClient(api_key="secret-token", base_url="https://api.example.com")
    session = _Session(get_responses=[_Response(200, payload=["not", "dict"])])
    assert asyncio.run(client.list_models_async(session)) == []  # type: ignore[arg-type]


def test_chat_completion_unconfigured_empty_choices_and_non_string_content() -> None:
    client = OpenAICompatibleClient(api_key="", base_url="https://api.example.com")
    with pytest.raises(RuntimeError, match="llm_client_not_configured"):
        asyncio.run(
            client.chat_completion_async(  # type: ignore[arg-type]
                _Session(),
                model="m",
                messages=[],
            )
        )

    configured = OpenAICompatibleClient(api_key="k", base_url="https://api.example.com/v1")
    empty = asyncio.run(
        configured.chat_completion_async(  # type: ignore[arg-type]
            _Session(post_responses=[_Response(200, payload={"choices": []})]),
            model="m",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=0,
        )
    )
    assert empty.text == ""

    non_string = asyncio.run(
        configured.chat_completion_async(  # type: ignore[arg-type]
            _Session(
                post_responses=[
                    _Response(200, payload={"choices": [{"message": {"content": 123}}]})
                ]
            ),
            model="m",
            messages=[{"role": "user", "content": "hi"}],
        )
    )
    assert non_string.text == "123"


def test_chat_completion_list_content_ignores_non_text_blocks() -> None:
    client = OpenAICompatibleClient(api_key="k", base_url="https://api.example.com")
    result = asyncio.run(
        client.chat_completion_async(  # type: ignore[arg-type]
            _Session(
                post_responses=[
                    _Response(
                        200,
                        payload={
                            "choices": [
                                {
                                    "message": {
                                        "content": [
                                            {"text": "one"},
                                            {"type": "image"},
                                            "bad",
                                        ]
                                    }
                                }
                            ],
                            "usage": {"tokens": 1},
                        },
                    )
                ]
            ),
            model="fallback-model",
            messages=[{"role": "user", "content": "hi"}],
        )
    )
    assert result.text == "one"
    assert result.model == "fallback-model"
    assert result.usage == {"tokens": 1}


def test_anthropic_messages_empty_and_error_paths() -> None:
    client = OpenAICompatibleClient(
        api_key="secret-token",
        base_url="https://api.anthropic.com",
        provider_preset="anthropic",
        auth_mode="x-api-key",
    )
    session = _Session(
        post_responses=[
            _Response(
                200,
                payload={
                    "content": [
                        {"type": "image", "text": "ignored"},
                        {"type": "text", "text": "answer"},
                    ]
                },
            )
        ]
    )
    result = asyncio.run(
        client.chat_completion_async(  # type: ignore[arg-type]
            session,
            model="claude",
            messages=[
                {"role": "tool", "content": ""},
                {"role": "tool", "content": []},
                {"role": "assistant", "content": ["bad", {"type": "image"}]},
                {"role": "system", "content": [{"text": "sys"}]},
                {"role": "system", "content": []},
            ],
            max_tokens=0,
        )
    )
    assert result.text == "answer"
    assert session.post_payloads[0]["messages"][0]["role"] == "user"
    assert session.post_payloads[0]["messages"][0]["content"] == "[empty]"
    assert session.post_payloads[0]["max_tokens"] == 1

    failing = _Session(
        post_responses=[
            _Response(500, text="secret-token failed"),
            _Response(500, text="secret-token failed"),
        ]
    )
    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(
            client.chat_completion_async(  # type: ignore[arg-type]
                failing,
                model="claude",
                messages=[],
            )
        )
    assert "secret-token" not in str(exc_info.value)


def test_discover_models_sync_uses_async_session(monkeypatch: pytest.MonkeyPatch) -> None:
    client = OpenAICompatibleClient(api_key="k", base_url="https://api.example.com")

    class _ClientSession:
        def __init__(self, timeout: object) -> None:
            self.timeout = timeout

        async def __aenter__(self) -> "_ClientSession":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    async def fake_list_models_async(session: object):
        return [SimpleNamespace(id="m")]

    monkeypatch.setattr("markflow.llm_client.aiohttp.ClientSession", _ClientSession)
    monkeypatch.setattr(client, "list_models_async", fake_list_models_async)
    assert client.discover_models_sync()[0].id == "m"
