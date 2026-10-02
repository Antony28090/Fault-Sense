"""LLM query rewriting: an operator's wording restated in manual vocabulary, used for retrieval only.

Operators describe symptoms ("trips on hot afternoons"); manuals describe faults ("device
overheating, ambient temperature too high"). The rewrite bridges that gap for search and reranking;
it is never shown to the operator and never treated as a detected fault code.
"""
from __future__ import annotations

from faultsense.llm.base import LLMError, LLMProvider

REWRITE_SYSTEM = (
    "You turn a shop-floor operator's description of a problem with an industrial variable-speed drive into a "
    "search query for the drive's manual. Restate it in the vocabulary such manuals use: the fault conditions the "
    "description points to (for example device overheating, DC bus overvoltage, input phase loss, motor overload, "
    "output phase loss, brake control error, communication interruption), the components involved and the "
    "operating situation. Keep it to one or two sentences. Copy any fault code the operator quotes verbatim. "
    "Never explain or guess what a fault code means, and do not add parameter codes. If the description is not "
    "about a drive, restate it faithfully without adding drive terms."
)
REWRITE_SCHEMA = {
    "type": "object",
    "properties": {"search_query": {"type": "string"}},
    "required": ["search_query"],
    "additionalProperties": False,
}


class QueryRewriter:
    def __init__(self, llm: LLMProvider):
        self._llm = llm

    def rewrite(self, query: str) -> str | None:
        """The rewritten query, or None when the LLM is unavailable (callers fall back to the original)."""
        try:
            answer = self._llm.complete_json(REWRITE_SYSTEM, query, REWRITE_SCHEMA)
        except LLMError:
            return None
        if not isinstance(answer, dict):
            return None
        text = str(answer.get("search_query", "")).strip()
        return text or None
