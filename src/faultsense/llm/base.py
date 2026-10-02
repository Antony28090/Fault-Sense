"""Provider-neutral LLM interface."""
from __future__ import annotations

from typing import Protocol


class LLMError(RuntimeError):
    """The LLM call failed or returned something unusable."""


class LLMRefusal(LLMError):
    """The model declined the request (stop_reason == 'refusal')."""


class LLMProvider(Protocol):
    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        """Return a JSON object that conforms to `schema`."""
