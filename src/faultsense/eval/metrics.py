"""Per-scenario results and the metrics computed over them."""
from __future__ import annotations

from dataclasses import dataclass, field

from faultsense.codes import code_key, confusable_variants
from faultsense.eval.scenarios import ExpectedSource


@dataclass
class ScenarioResult:
    id: str
    type: str
    reviewed: bool
    top_score: float | None = None
    expanded_query: str | None = None
    retrieved: list[dict] = field(default_factory=list)
    detected_codes: list[str] = field(default_factory=list)
    hit_at_5: bool | None = None
    code_match: bool | None = None
    status: str | None = None
    cause_at_3: bool | None = None
    cause_pairs: list[list] = field(default_factory=list)
    citations_correct: int = 0
    citations_total: int = 0
    raw_hallucination: bool | None = None
    final_hallucination: bool | None = None
    unknown_identifiers: list[str] = field(default_factory=list)
    refusal_correct: bool | None = None
    false_escalation: bool | None = None
    latency_ms: int | None = None
    translation_fallbacks: int = 0  # translated sentences shown in English because they failed the check
    translation_total: int = 0
    error: str | None = None
    answer: dict | None = None


def pages_hit(retrieved: list[dict], expected: list[ExpectedSource]) -> bool:
    for item in retrieved:
        for source in expected:
            if item["manual"] == source.manual and any(item["page_start"] <= p <= item["page_end"] for p in source.pages):
                return True
    return False


def hit_at_k(retrieved: list[dict], expected: list[ExpectedSource], k: int = 5) -> bool | None:
    return pages_hit(retrieved[:k], expected) if expected else None


def code_match(detected: list[str], expected: list[str]) -> bool | None:
    if not expected:
        return None
    found = {code_key(code) for code in detected}
    return all(code_key(e) in found or bool(confusable_variants(code_key(e)) & found) for e in expected)


def _rate(values) -> dict:
    applicable = [v for v in values if v is not None]
    return {"value": (sum(applicable) / len(applicable)) if applicable else None, "n": len(applicable)}


def _percentile(sorted_values: list[int], p: int) -> int | None:
    if not sorted_values:
        return None
    index = round(p / 100 * (len(sorted_values) - 1))
    return sorted_values[max(0, min(len(sorted_values) - 1, index))]


def summarize(results: list[ScenarioResult]) -> dict:
    latencies = sorted(r.latency_ms for r in results if r.latency_ms is not None)
    correct = sum(r.citations_correct for r in results)
    total = sum(r.citations_total for r in results)
    translated = sum(r.translation_total for r in results)
    return {
        "scenarios": len(results),
        "reviewed": sum(r.reviewed for r in results),
        "errors": sum(r.error is not None for r in results),
        "metrics": {
            "retrieval_hit_at_5": _rate(r.hit_at_5 for r in results),
            "fault_code_match": _rate(r.code_match for r in results),
            "cause_in_top_3": _rate(r.cause_at_3 for r in results),
            "citation_accuracy": {"value": correct / total if total else None, "n": total},
            "hallucination_raw": _rate(r.raw_hallucination for r in results),
            "hallucination_final": _rate(r.final_hallucination for r in results),
            "out_of_scope_refusal": _rate(r.refusal_correct for r in results),
            "false_escalation": _rate(r.false_escalation for r in results),
            "translation_fallback": {
                "value": (sum(r.translation_fallbacks for r in results) / translated) if translated else None,
                "n": translated,
            },
        },
        "latency_ms": {"p50": _percentile(latencies, 50), "p95": _percentile(latencies, 95)},
    }


def answer_text(response) -> str:
    """Every operator-visible text field of a diagnosis, for the identifier check."""
    parts: list[str] = []
    for cause in response.probable_causes:
        parts += [cause.cause, cause.fault_code or ""]
    parts += [step.action for step in response.corrective_actions]
    parts += [warning.text for warning in response.safety_warnings]
    return "\n".join(part for part in parts if part)


def cause_at_3(answer_causes: list[str], expected: list[str], embed, threshold: float) -> tuple[bool | None, list[list]]:
    """True when some expected cause is matched (cosine >= threshold) by one of the top three answer causes.
    Pairs are returned so a person can check the matches."""
    if not expected:
        return None, []
    top = answer_causes[:3]
    if not top:
        return False, []
    vectors = embed(list(expected) + list(top))
    similarities = vectors[: len(expected)] @ vectors[len(expected):].T
    pairs = []
    for i, wanted in enumerate(expected):
        j = int(similarities[i].argmax())
        pairs.append([wanted, top[j], round(float(similarities[i, j]), 3)])
    return any(score >= threshold for _, _, score in pairs), pairs


def citation_accuracy(response, expected: list[ExpectedSource]) -> tuple[int, int]:
    """(correct, total) over cause and step citations; citations of the safety anchor are not counted."""
    refs = {source.id: source for source in response.sources}
    correct = total = 0
    for item in [*response.probable_causes, *response.corrective_actions]:
        for citation in item.citations:
            ref = refs.get(citation.source_id)
            if ref is not None and ref.kind == "safety":
                continue
            total += 1
            if ref and any(src.manual == ref.manual and any(ref.page_start <= p <= ref.page_end for p in src.pages)
                           for src in expected):
                correct += 1
    return correct, total
