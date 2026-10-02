import json

import httpx
import pytest

from faultsense.config import Settings
from faultsense.llm import get_provider
from faultsense.llm.base import LLMError
from faultsense.llm.ollama_provider import OllamaProvider


def provider_with(handler, **kwargs):
    requests = []

    def record(request):
        requests.append(request)
        return handler(request)

    client = httpx.Client(transport=httpx.MockTransport(record))
    return OllamaProvider("qwen3.5:4b", client=client, **kwargs), requests


def chat_reply(content, done_reason="stop"):
    return lambda request: httpx.Response(200, json={"message": {"role": "assistant", "content": content},
                                                     "done": True, "done_reason": done_reason})


def test_request_enforces_the_schema_and_turns_off_sampling_and_thinking():
    provider, requests = provider_with(chat_reply('{"status": "diagnosis"}'), num_ctx=16384)
    assert provider.complete_json("sys", "user", {"type": "object"}) == {"status": "diagnosis"}
    [request] = requests
    assert str(request.url) == "http://localhost:11434/api/chat"
    body = json.loads(request.content)
    assert body["model"] == "qwen3.5:4b"
    system, user = body["messages"]
    assert system["role"] == "system" and system["content"].startswith("sys")
    assert user == {"role": "user", "content": "user"}
    assert body["format"] == {"type": "object"}
    assert body["stream"] is False and body["think"] is False
    assert body["options"]["temperature"] == 0 and body["options"]["num_ctx"] == 16384


def test_truncated_or_invalid_json_raises_llm_error():
    truncated, _ = provider_with(chat_reply('{"status": "diag', done_reason="length"))
    with pytest.raises(LLMError, match="truncated"):
        truncated.complete_json("s", "u", {})
    invalid, _ = provider_with(chat_reply("not json"))
    with pytest.raises(LLMError, match="invalid JSON"):
        invalid.complete_json("s", "u", {})


def test_ollama_errors_become_llm_errors():
    missing, _ = provider_with(lambda request: httpx.Response(404, json={"error": "model 'qwen3.5:4b' not found"}))
    with pytest.raises(LLMError, match="not found"):
        missing.complete_json("s", "u", {})

    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)

    down, _ = provider_with(refuse)
    with pytest.raises(LLMError, match="ollama serve"):
        down.complete_json("s", "u", {})


def test_get_provider_builds_ollama_from_settings():
    settings = Settings(_env_file=None, llm_provider="ollama", llm_model="gemma4:e4b",
                        ollama_url="http://gpu-box:11434", ollama_num_ctx=8192)
    provider = get_provider(settings)
    assert isinstance(provider, OllamaProvider)
    assert (provider._model, provider._base_url, provider._num_ctx) == ("gemma4:e4b", "http://gpu-box:11434", 8192)


def test_the_model_is_shown_the_schema_it_must_follow():
    # Ollama enforces `format` while decoding but never shows it to the model; without the schema in the
    # prompt, local models could not know "diagnosis" was a valid status and declined every question.
    schema = {"type": "object", "properties": {"status": {"type": "string", "enum": ["diagnosis", "insufficient_evidence"]}}}
    provider, requests = provider_with(chat_reply('{"status": "diagnosis"}'))
    provider.complete_json("sys", "user", schema)
    system = json.loads(requests[0].content)["messages"][0]["content"]
    assert json.dumps(schema) in system
