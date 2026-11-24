import json

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic import SecretStr

from app.config import settings
from app.interview import provider


def mock_openai(monkeypatch, result, headers=None):
    requests = []

    def respond(request):
        requests.append((request.method, str(request.url), json.loads(request.content)))
        if isinstance(result, type) and issubclass(result, httpx.TransportError):
            raise result("simulated transport failure", request=request)
        return httpx.Response(result[0], json=result[1], headers=headers)

    def client(**kwargs):
        return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))

    monkeypatch.setattr(provider, "AsyncOpenAI", client)
    monkeypatch.setattr(settings, "INTERVIEW_LLM_MODEL", "configured-interview-model")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", SecretStr("mock-key-for-transport"))
    return requests


def response(status="completed", part=None):
    return {
        "id": "resp_mock", "object": "response", "created_at": 0, "status": status,
        "model": "reported-model",
        "output": [{
            "id": "msg_mock", "type": "message", "role": "assistant", "status": status,
            "content": [part or {"type": "output_text", "text": "我先去看了窗邊。", "annotations": []}],
        }],
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    }


async def test_responses_request_and_completion(monkeypatch):
    requests = mock_openai(monkeypatch, (200, response()))
    messages = [
        {"role": "user", "content": "你去哪裡？"},
        {"role": "assistant", "content": "我去找座位。"},
        {"role": "user", "content": "先去了哪裡？"},
    ]
    result = await provider.OpenAIInterviewProvider().generate("扮演林沂", messages)
    assert result.content == "我先去看了窗邊。"
    assert result.model == "reported-model"
    assert result.usage.total_tokens == 15
    assert requests == [("POST", "https://api.openai.com/v1/responses", {
        "model": "configured-interview-model", "instructions": "扮演林沂", "input": messages,
        "max_output_tokens": settings.INTERVIEW_LLM_MAX_OUTPUT_TOKENS, "store": False, "truncation": "disabled",
    })]


@pytest.mark.parametrize(("payload", "code"), [
    ((200, response("incomplete")), "invalid_reply"),
    ((200, response(part={"type": "refusal", "refusal": "test"})), "invalid_reply"),
    ((400, {"error": {"code": "context_length_exceeded", "message": "private"}}), "context_limit"),
    ((401, {"error": {"code": "invalid_api_key", "message": "private"}}), "openai_auth"),
    ((404, {"error": {"code": "model_not_found", "message": "private"}}), "openai_model"),
    ((429, {"error": {"code": "insufficient_quota", "message": "private"}}), "openai_quota"),
    ((429, {"error": {"code": "credit_balance_exhausted"}}), "openai_quota"),
    ((429, {"error": {"code": "organization_usage_limit_exceeded"}}), "openai_quota"),
    ((429, {"error": {"code": "rate_limit_exceeded", "message": "private"}}), "openai_rate_limit"),
    ((500, {"error": {"message": "private"}}), "openai_unavailable"),
    (httpx.ConnectError, "openai_connection"),
    (httpx.ReadTimeout, "openai_timeout"),
])
async def test_responses_failures_are_normalized(monkeypatch, payload, code):
    requests = mock_openai(monkeypatch, payload)
    with pytest.raises(provider.GenerationError, match=f"^{code}$"):
        await provider.OpenAIInterviewProvider().generate("角色", [{"role": "user", "content": "你好"}])
    assert len(requests) == 1


async def test_rate_limit_preserves_retry_after(monkeypatch):
    payload = (429, {"error": {"code": "rate_limit_exceeded"}})
    mock_openai(monkeypatch, payload, {"Retry-After": "90"})
    with pytest.raises(provider.GenerationError, match="^openai_rate_limit$") as error:
        await provider.OpenAIInterviewProvider().generate("角色", [{"role": "user", "content": "你好"}])
    assert error.value.retry_after == 90


@pytest.mark.parametrize(("key", "model", "code"), [
    ("", "configured-model", "missing_key"),
    ("mock-key", "", "missing_model"),
])
async def test_missing_configuration_does_not_create_client(monkeypatch, key, model, code):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", SecretStr(key))
    monkeypatch.setattr(settings, "INTERVIEW_LLM_MODEL", model)

    def unexpected(**kwargs):
        pytest.fail("Unexpected OpenAI client")

    monkeypatch.setattr(provider, "AsyncOpenAI", unexpected)
    with pytest.raises(provider.GenerationError, match=f"^{code}$"):
        await provider.OpenAIInterviewProvider().generate("角色", [{"role": "user", "content": "你好"}])
