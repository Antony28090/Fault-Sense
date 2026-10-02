from types import SimpleNamespace

import anthropic
import pytest

from faultsense.config import Settings
from faultsense.llm import get_provider
from faultsense.llm.anthropic_provider import AnthropicProvider
from faultsense.llm.base import LLMError, LLMRefusal
from faultsense.llm.fake import FakeLLM


class StubMessages:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.kwargs = response, error, None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.response


def stub_client(response=None, error=None):
    messages = StubMessages(response, error)
    return SimpleNamespace(beta=SimpleNamespace(messages=messages)), messages


def text_response(text, stop_reason="end_turn"):
    return SimpleNamespace(stop_reason=stop_reason, content=[
        SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text),
    ])


class FakeConnectionError(anthropic.APIConnectionError):
    def __init__(self):  # skip the SDK constructor, which needs a real request object
        Exception.__init__(self, "connection refused")


def test_request_uses_structured_output_fallbacks_and_effort():
    client, messages = stub_client(text_response('{"status": "diagnosis"}'))
    provider = AnthropicProvider("claude-opus-5-5", effort="high", client=client)
    assert provider.complete_json("sys", "user", {"type": "object"}) == {"status": "diagnosis"}
    kwargs = messages.kwargs
    assert (kwargs["model"], kwargs["system"]) == ("claude-opus-5-5", "sys")
    assert kwargs["messages"] == [{"role": "user", "content": "user"}]
    assert kwargs["output_config"] == {"format": {"type": "json_schema", "schema": {"type": "object"}}, "effort": "high"}
    assert kwargs["betas"] == ["server-side-fallback-2026-07-01"]
    assert kwargs["fallbacks"] == "default"


def test_refusal_raises_llm_refusal():
    client, _ = stub_client(text_response("", stop_reason="refusal"))
    with pytest.raises(LLMRefusal):
        AnthropicProvider("m", client=client).complete_json("s", "u", {})


@pytest.mark.parametrize("response", [text_response('{"a":', stop_reason="max_tokens"), text_response("not json")])
def test_truncated_or_invalid_json_raises_llm_error(response):
    client, _ = stub_client(response)
    with pytest.raises(LLMError):
        AnthropicProvider("m", client=client).complete_json("s", "u", {})


def test_connection_errors_become_llm_errors():
    client, _ = stub_client(error=FakeConnectionError())
    with pytest.raises(LLMError, match="connection"):
        AnthropicProvider("m", client=client).complete_json("s", "u", {})


def test_fake_llm_replays_scripted_answers_and_errors():
    llm = FakeLLM([{"ok": 1}, LLMError("boom")])
    assert llm.complete_json("s", "u", {}) == {"ok": 1}
    with pytest.raises(LLMError):
        llm.complete_json("s", "u2", {})
    assert [call["user"] for call in llm.calls] == ["u", "u2"]


def test_get_provider_builds_anthropic_and_rejects_unknown_providers():
    assert isinstance(get_provider(Settings(_env_file=None, llm_api_key="test-key")), AnthropicProvider)
    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        get_provider(Settings(_env_file=None, llm_provider="nope"))


class FakeResponseValidationError(anthropic.APIResponseValidationError):
    def __init__(self):  # an APIError that is neither a connection nor a status error
        Exception.__init__(self, "response did not match the expected schema")


def test_any_other_sdk_error_becomes_an_llm_error():
    client, _ = stub_client(error=FakeResponseValidationError())
    with pytest.raises(LLMError, match="schema"):
        AnthropicProvider("m", client=client).complete_json("s", "u", {})
