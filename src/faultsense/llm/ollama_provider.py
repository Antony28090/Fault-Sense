"""Local open-weight models (Qwen, Gemma, Sarvam, ...) through Ollama's chat API.

Ollama constrains decoding to the JSON schema, so answers always parse; whether they are grounded
is still the guard's job. Unlike the Anthropic API, Ollama does not show the schema to the model, so
it is added to the system prompt: without it the models never learned that "diagnosis" was a valid
status and declined every question. Sampling is greedy (temperature 0) and thinking is off by default:
on a laptop GPU, reasoning tokens cost tens of seconds per answer.
"""
from __future__ import annotations

import json

import httpx

from faultsense.llm.base import LLMError

MAX_OUTPUT_TOKENS = 4096  # bounds a small model that loops inside a JSON array
SCHEMA_INSTRUCTION = "\n\nAnswer with one JSON object that follows this JSON schema:\n"


class OllamaProvider:
    def __init__(self, model: str, base_url: str = "http://localhost:11434", num_ctx: int = 16384,
                 think: bool = False, timeout: float = 600.0, client: httpx.Client | None = None):
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._num_ctx = num_ctx  # Ollama's default context is too short for 8+ manual passages
        self._think = think
        self._client = client or httpx.Client(timeout=timeout)

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": f"{system}{SCHEMA_INSTRUCTION}{json.dumps(schema)}"},
                {"role": "user", "content": user},
            ],
            "format": schema,
            "stream": False,
            "think": self._think,
            "options": {"temperature": 0, "num_ctx": self._num_ctx, "num_predict": MAX_OUTPUT_TOKENS},
        }
        try:
            response = self._client.post(f"{self._base_url}/api/chat", json=body)
        except httpx.ConnectError as exc:
            raise LLMError(f"Ollama is not reachable at {self._base_url}; start it with `ollama serve`") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama request failed: {exc}") from exc
        if response.status_code != 200:
            try:
                detail = response.json().get("error", response.text)
            except ValueError:
                detail = response.text
            raise LLMError(f"Ollama error {response.status_code}: {detail}")
        data = response.json()
        if data.get("done_reason") == "length":
            raise LLMError("LLM output was truncated (context or output token limit)")
        text = (data.get("message") or {}).get("content", "")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"LLM returned invalid JSON: {exc}") from exc
