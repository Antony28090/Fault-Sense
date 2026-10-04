"""Runs scenarios through the retriever, or in full mode through the diagnosis service.

Full mode scores retrieval from the diagnosis response itself, so the sources the LLM saw are the
ones scored (query rewriting varies between calls, so a second search could differ).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from faultsense.diagnosis.guard import KnownIdentifiers, unknown_identifiers
from faultsense.eval.metrics import (
    ScenarioResult, answer_text, cause_at_3, citation_accuracy, code_match, hit_at_k,
)
from faultsense.eval.scenarios import Scenario
from faultsense.manifest import MachineSpec


@dataclass
class AnswerScorer:
    embed: Callable[[list[str]], np.ndarray]
    known: KnownIdentifiers | Callable[[list[str]], KnownIdentifiers]  # fixed set, or per answer's manuals
    cause_threshold: float = 0.75


def _record_retrieval(result: ScenarioResult, scenario: Scenario, top_score: float, expanded_query: str | None,
                      retrieved: list[dict], detected_codes: list[str]) -> None:
    result.top_score = round(top_score, 3)
    result.expanded_query = expanded_query
    result.retrieved = retrieved
    result.detected_codes = detected_codes
    result.hit_at_5 = hit_at_k(retrieved, scenario.expected_sources, 5)
    if scenario.type == "fault_code":
        result.code_match = code_match(detected_codes, scenario.expected_fault_codes)


def _score_retrieval(result: ScenarioResult, scenario: Scenario, retriever, machines: dict[str, MachineSpec]) -> None:
    manual_ids = [machines[scenario.machine_id].manual] if scenario.machine_id else None
    retrieval = retriever.retrieve(scenario.query, manual_ids)
    retrieved = [
        {"manual": c.chunk.manual_id, "page_start": c.chunk.page_start, "page_end": c.chunk.page_end,
         "kind": c.chunk.kind, "heading": c.chunk.heading_path, "score": round(c.score, 3)}
        for c in retrieval.chunks
    ]
    _record_retrieval(result, scenario, retrieval.top_score, retrieval.expanded_query, retrieved,
                      [m.hit.code for m in retrieval.matched_codes])


def _score_answer(result: ScenarioResult, scenario: Scenario, service, scorer: AnswerScorer) -> None:
    response = service.diagnose(scenario.query, scenario.machine_id)
    retrieved = [  # sources with a score came from retrieval; the rest are safety passages the service added
        {"manual": s.manual, "page_start": s.page_start, "page_end": s.page_end, "kind": s.kind,
         "heading": s.heading, "score": s.score}
        for s in response.sources if s.score is not None
    ]
    _record_retrieval(result, scenario, response.meta.retrieval_top_score, response.meta.search_query, retrieved,
                      [m.code for m in response.matched_fault_codes])
    result.answer = response.model_dump(mode="json")
    result.status = response.status
    result.latency_ms = response.meta.latency_ms
    translation = response.translation
    if translation is not None and translation.available:
        items = translation.causes + translation.steps + translation.safety_warnings
        result.translation_total = len(items)
        result.translation_fallbacks = sum(item.fallback for item in items)
    if scenario.expected_behavior == "escalate":
        result.refusal_correct = response.status == "escalate"
    else:
        result.false_escalation = response.status == "escalate"
        causes = [cause.cause for cause in response.probable_causes]
        result.cause_at_3, result.cause_pairs = cause_at_3(causes, scenario.expected_causes, scorer.embed,
                                                           scorer.cause_threshold)
        result.citations_correct, result.citations_total = citation_accuracy(response, scenario.expected_sources)
    manuals = sorted({source.manual for source in response.sources})
    known = scorer.known(manuals) if callable(scorer.known) else scorer.known
    result.unknown_identifiers = unknown_identifiers(answer_text(response), known)
    result.final_hallucination = bool(result.unknown_identifiers)
    result.raw_hallucination = result.final_hallucination or any(
        "unknown identifier" in violation for violation in response.meta.first_pass_violations
    )


def run_eval(scenarios: list[Scenario], retriever, machines: dict[str, MachineSpec], service=None,
             scorer: AnswerScorer | None = None,
             progress: Callable[[ScenarioResult], None] | None = None) -> list[ScenarioResult]:
    results = []
    for scenario in scenarios:
        result = ScenarioResult(scenario.id, scenario.type, scenario.reviewed)
        try:
            if service is not None and scorer is not None:
                _score_answer(result, scenario, service, scorer)
            else:
                _score_retrieval(result, scenario, retriever, machines)
        except Exception as exc:  # one broken scenario must not abort the whole run
            result.error = f"{type(exc).__name__}: {exc}"
        results.append(result)
        if progress:
            progress(result)
    return results
