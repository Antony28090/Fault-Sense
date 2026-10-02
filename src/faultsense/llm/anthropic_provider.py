"""Claude via the Anthropic SDK, with structured JSON output and server-side refusal fallbacks."""
from __future__ import annotations

import json

import anthropic

from faultsense.llm.base import LLMError, LLMRefusal

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider:
    def __init__(self, model: str, api_key: str = "", effort: str = "high",
                 client: anthropic.Anthropic | None = None):
        self._model = model
        self._effort = effort
        # Without an explicit key the SDK uses ANTHROPIC_API_KEY or an `ant auth login` profile.
        self._client = client or (anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic())

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        try:
            response = self._client.beta.messages.create(
                model=self._model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"format": {"type": "json_schema", "schema": schema}, "effort": self._effort},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.APIConnectionError as exc:
            raise LLMError(f"LLM connection failed: {exc}") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("LLM rate limited; try again shortly") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"LLM API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIError as exc:  # anything else the SDK raises, e.g. an unparseable response
            raise LLMError(f"LLM request failed: {exc}") from exc
        if response.stop_reason == "refusal":
            raise LLMRefusal("the model declined this request")
        if response.stop_reason == "max_tokens":
            raise LLMError("LLM output was truncated (max_tokens)")
        text = next((block.text for block in response.content if block.type == "text"), None)
        if text is None:
            raise LLMError("LLM returned no text block")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"LLM returned invalid JSON: {exc}") from exc
