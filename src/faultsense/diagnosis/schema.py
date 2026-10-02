"""Public response contract and the LLM-facing structured-output schema.

The LLM only ever returns source ids; the service resolves them into citations with manual + page.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Citation(BaseModel):
    source_id: str
    manual: str
    manual_title: str
    page: int


class Cause(BaseModel):
    rank: int
    cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    fault_code: str | None = None
    citations: list[Citation]


class Step(BaseModel):
    step: int
    action: str
    requires_isolation: bool
    citations: list[Citation]


class SafetyWarning(BaseModel):
    text: str
    citations: list[Citation]


class SourceRef(BaseModel):
    id: str
    chunk_id: str
    manual: str
    manual_title: str
    family: str
    page_start: int
    page_end: int
    heading: str
    kind: str
    score: float | None = None  # rerank score of a retrieved passage; None for safety passages the service adds


class MatchedCode(BaseModel):
    code: str
    manual: str
    name: str
    page: int
    fuzzy: bool = False


class Escalation(BaseModel):
    reason: str
    summary: str
    sources_considered: list[SourceRef]
    collect: list[str]


class Meta(BaseModel):
    retrieval_top_score: float
    llm_called: bool = False
    guard_retries: int = 0
    first_pass_violations: list[str] = []
    final_violations: list[str] = []
    latency_ms: int = 0
    llm_note: str = ""  # the LLM's own explanation when it declined; for engineers, not shown as the reason
    search_query: str | None = None  # the LLM rewrite used for search when no code was typed; for engineers
    named_models: list[str] = []  # drive models the operator named, e.g. ["ATV630"]


class DiagnosisResponse(BaseModel):
    status: Literal["diagnosis", "escalate"]
    query: str
    machine_id: str | None
    language: str
    matched_fault_codes: list[MatchedCode]
    probable_causes: list[Cause]
    corrective_actions: list[Step]
    safety_warnings: list[SafetyWarning]
    escalation: Escalation | None
    sources: list[SourceRef]
    meta: Meta


class LLMCause(BaseModel):
    cause: str
    confidence: float
    fault_code: str
    source_ids: list[str]


class LLMStep(BaseModel):
    action: str
    requires_isolation: bool
    source_ids: list[str]


class LLMWarning(BaseModel):
    text: str
    source_ids: list[str]


class LLMDiagnosis(BaseModel):
    status: Literal["diagnosis", "insufficient_evidence"]
    insufficient_reason: str
    probable_causes: list[LLMCause]
    corrective_actions: list[LLMStep]
    safety_warnings: list[LLMWarning]


_IDS = {"type": "array", "items": {"type": "string"}}


def _object(properties: dict) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


LLM_OUTPUT_SCHEMA = _object({
    "status": {"type": "string", "enum": ["diagnosis", "insufficient_evidence"]},
    "insufficient_reason": {"type": "string"},
    "probable_causes": {"type": "array", "items": _object({
        "cause": {"type": "string"},
        "confidence": {"type": "number"},
        "fault_code": {"type": "string"},
        "source_ids": _IDS,
    })},
    "corrective_actions": {"type": "array", "items": _object({
        "action": {"type": "string"},
        "requires_isolation": {"type": "boolean"},
        "source_ids": _IDS,
    })},
    "safety_warnings": {"type": "array", "items": _object({
        "text": {"type": "string"},
        "source_ids": _IDS,
    })},
})
