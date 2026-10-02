"""Diagnosis pipeline: retrieve -> evidence gate -> LLM -> guard (one retry) -> cited answer or escalation."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable

from pydantic import ValidationError

from faultsense.diagnosis.guard import KnownIdentifiers, check_llm_output
from faultsense.drives import named_drive_models
from faultsense.diagnosis.prompt import SYSTEM_PROMPT, PromptSource, build_user_prompt
from faultsense.diagnosis.schema import (
    LLM_OUTPUT_SCHEMA, Cause, Citation, DiagnosisResponse, Escalation, LLMDiagnosis, MatchedCode, Meta,
    SafetyWarning, SourceRef, Step,
)
from faultsense.language import IdentityLanguageLayer, LanguageLayer
from faultsense.llm.base import LLMError, LLMProvider
from faultsense.manifest import MachineSpec, ManualSpec
from faultsense.retrieval.retriever import RetrievalResult
from faultsense.telemetry import NullTelemetrySource, TelemetrySource

COLLECT_CHECKLIST = [
    "The exact code on the drive display, and whether it is flashing",
    "When it happens: at start, while accelerating, at steady speed, while braking or at stop",
    "How often and since when; anything changed recently (motor, cables, parameters, load, ambient)",
    "Drive model and rating-plate details",
]
TELEMETRY_WINDOW = timedelta(minutes=30)
Progress = Callable[[str, dict], None]  # (stage, detail): "search", "found", "write", "retry"


class UnknownMachine(LookupError):
    def __init__(self, machine_id: str):
        super().__init__(machine_id)
        self.machine_id = machine_id


@dataclass(frozen=True)
class _Source:
    ref: SourceRef
    text: str


def _code_line(match) -> str:
    line = f"{match.hit.code} ({match.hit.manual_id} p.{match.hit.page})"
    if match.fuzzy:
        line += f": the operator typed '{match.token}', which looks the same on the drive's 7-segment display"
    return line


def _repair_note(violations: list[str]) -> str:
    listed = "\n".join(f"- {v}" for v in violations)
    return ("\n\nYOUR PREVIOUS ANSWER WAS REJECTED by the grounding check:\n" + listed +
            "\nAnswer again. Cite only the listed source ids and use only codes and names that appear in the SOURCES.")


class DiagnosisService:
    def __init__(self, retriever, repo, llm: LLMProvider, manuals: dict[str, ManualSpec],
                 machines: dict[str, MachineSpec], language: LanguageLayer | None = None,
                 telemetry: TelemetrySource | None = None, evidence_threshold: float = 0.30,
                 clock: Callable[[], float] = time.perf_counter):
        self._retriever = retriever
        self._repo = repo
        self._llm = llm
        self._manuals = manuals
        self._machines = machines
        self._language = language or IdentityLanguageLayer()
        self._telemetry = telemetry or NullTelemetrySource()
        self._threshold = evidence_threshold
        self._clock = clock
        self._by_manual: dict[str, tuple[set[str], set[str]]] | None = None
        self._model_manual = {model.upper(): spec.id for spec in manuals.values() for model in spec.models}

    def known_identifiers(self, manual_ids: list[str] | None = None) -> KnownIdentifiers:
        """Identifiers of the given manuals (all manuals when None): an answer about one drive may only
        use that drive's codes and names."""
        if self._by_manual is None:
            self._by_manual = self._repo.known_identifiers_by_manual()
        codes: set[str] = set()
        labels: set[str] = set()
        for manual_id in (manual_ids if manual_ids is not None else list(self._by_manual)):
            manual_codes, manual_labels = self._by_manual.get(manual_id, (set(), set()))
            codes |= manual_codes
            labels |= manual_labels
        return KnownIdentifiers(frozenset(codes), frozenset(labels))

    def health(self) -> dict:
        try:
            database = "ok" if self._repo.ping() else "unreachable"
        except Exception as exc:  # health must report, not raise
            database = f"unreachable: {type(exc).__name__}"
        return {"manuals": sorted(self._manuals), "machines": sorted(self._machines), "database": database}

    def passage(self, chunk_id: str) -> dict | None:
        """The manual text behind a citation, for the operator page's passage viewer."""
        chunk = self._repo.get_chunks([chunk_id]).get(chunk_id)
        if chunk is None:
            return None
        spec = self._manuals.get(chunk.manual_id)
        return {"chunk_id": chunk.id, "manual": chunk.manual_id, "family": spec.family if spec else chunk.manual_id,
                "title": spec.title if spec else chunk.manual_id, "heading": chunk.heading_path,
                "page_start": chunk.page_start, "page_end": chunk.page_end, "kind": chunk.kind, "text": chunk.text}

    def diagnose(self, query: str, machine_id: str | None = None, progress: Progress | None = None) -> DiagnosisResponse:
        started = self._clock()
        emit = progress or (lambda stage, detail: None)
        if machine_id is not None and machine_id not in self._machines:
            raise UnknownMachine(machine_id)
        text_en, language = self._language.to_english(query)
        named = named_drive_models(text_en)
        emit("search", {"models": named})
        covered = sorted({self._model_manual[m] for m in named if m in self._model_manual})
        if named and not covered:
            # Only drives without a manual were named: answering from another drive's manual would mislead.
            meta = Meta(retrieval_top_score=0.0, named_models=named)
            reason = (f"FaultSense has no manual for the {', '.join(named)}. "
                      f"It has manuals for these drives: {self._coverage()}.")
            return self._finish(self._escalation(query, machine_id, language, [], [], reason, meta), started, language)
        # A model named in the question beats the machine choice, which may be left over from an earlier question.
        manual_ids = covered or ([self._machines[machine_id].manual] if machine_id else None)
        result = self._retriever.retrieve(text_en, manual_ids)
        sources = self._sources(result, manual_ids)
        emit("found", {"codes": [m.hit.code for m in result.matched_codes], "pages": len(result.chunks),
                       "top": self._top(result)})
        matched = [MatchedCode(code=m.hit.code, manual=m.hit.manual_id, name=m.hit.name, page=m.hit.page, fuzzy=m.fuzzy)
                   for m in result.matched_codes]
        meta = Meta(retrieval_top_score=round(result.top_score, 3), search_query=result.expanded_query,
                    named_models=named)

        def escalate(reason: str) -> DiagnosisResponse:
            response = self._escalation(query, machine_id, language, matched, sources, reason, meta)
            return self._finish(response, started, language)

        if not result.matched_codes and result.top_score < self._threshold:
            return escalate(f"No fault code was recognised and the closest manual passage scored "
                            f"{result.top_score:.2f}, below the evidence threshold of {self._threshold:.2f}.")
        valid_ids = {s.ref.id for s in sources}
        safety_ids = {s.ref.id for s in sources if s.ref.kind == "safety"}
        readings = self._telemetry.recent(machine_id, TELEMETRY_WINDOW) if machine_id else []
        user = build_user_prompt(text_en, [self._prompt_source(s) for s in sources],
                                 machine=self._machine_label(machine_id), telemetry=readings or None,
                                 recognised_codes=[_code_line(m) for m in result.matched_codes])
        known = self.known_identifiers(sorted({s.ref.manual for s in sources}))
        meta.llm_called = True
        emit("write", {})
        try:
            parsed, violations = self._ask(user, valid_ids, safety_ids, known)
            meta.first_pass_violations = violations
            if violations:
                meta.guard_retries = 1
                emit("retry", {"problems": len(violations)})
                parsed, violations = self._ask(user + _repair_note(violations), valid_ids, safety_ids, known)
        except LLMError as exc:
            return escalate(f"The language model could not produce an answer ({exc}).")
        meta.final_violations = violations
        if violations:
            return escalate("The drafted answer failed the grounding checks twice: " + "; ".join(violations[:3]) + ".")
        if parsed.status == "insufficient_evidence":
            # The LLM's explanation is unchecked text, so it is kept for engineers and never shown as the reason.
            meta.llm_note = parsed.insufficient_reason
            return escalate("The retrieved manual passages do not cover this problem well enough to name a cause.")
        response = self._answer(query, machine_id, language, matched, sources, parsed, result, meta)
        return self._finish(response, started, language)

    def _top(self, result: RetrievalResult) -> dict | None:
        if not result.chunks:
            return None
        chunk = result.chunks[0].chunk
        spec = self._manuals.get(chunk.manual_id)
        return {"manual": chunk.manual_id, "family": spec.family if spec else chunk.manual_id,
                "page": chunk.page_start, "heading": chunk.heading_path}

    def _coverage(self) -> str:
        return ", ".join(f"{spec.family} series" if len(spec.models) > 1 else spec.family
                         for spec in sorted(self._manuals.values(), key=lambda s: s.id))

    def _ask(self, user: str, valid_ids: set[str], safety_ids: set[str],
             known: KnownIdentifiers) -> tuple[LLMDiagnosis | None, list[str]]:
        raw = self._llm.complete_json(SYSTEM_PROMPT, user, LLM_OUTPUT_SCHEMA)
        try:
            parsed = LLMDiagnosis.model_validate(raw)
        except ValidationError as exc:
            first = exc.errors()[0]
            location = ".".join(str(part) for part in first["loc"])
            return None, [f"schema: {location} {first['msg']}"]
        return parsed, check_llm_output(parsed, valid_ids, safety_ids, known)

    def _sources(self, result: RetrievalResult, manual_ids: list[str] | None) -> list[_Source]:
        sources = [_Source(self._ref(f"S{n}", rc.chunk, round(rc.score, 3)), rc.chunk.text)
                   for n, rc in enumerate(result.chunks, 1)]
        involved = manual_ids or list(dict.fromkeys(rc.chunk.manual_id for rc in result.chunks))
        seen = {rc.chunk.id for rc in result.chunks}
        for chunk in self._repo.safety_chunks(involved):
            if chunk.id not in seen:
                seen.add(chunk.id)
                sources.append(_Source(self._ref(f"S{len(sources) + 1}", chunk), chunk.text))
        return sources

    def _ref(self, source_id: str, chunk, score: float | None = None) -> SourceRef:
        spec = self._manuals.get(chunk.manual_id)
        return SourceRef(
            id=source_id, chunk_id=chunk.id, manual=chunk.manual_id,
            manual_title=spec.title if spec else chunk.manual_id, family=spec.family if spec else "",
            page_start=chunk.page_start, page_end=chunk.page_end, heading=chunk.heading_path, kind=chunk.kind,
            score=score,
        )

    @staticmethod
    def _prompt_source(source: _Source) -> PromptSource:
        r = source.ref
        return PromptSource(r.id, r.manual_title, r.family, r.page_start, r.page_end, r.heading, r.kind, source.text)

    def _machine_label(self, machine_id: str | None) -> str | None:
        if not machine_id:
            return None
        spec = self._manuals.get(self._machines[machine_id].manual)
        return f"{machine_id} ({spec.family})" if spec else machine_id

    def _answer(self, query, machine_id, language, matched, sources, parsed: LLMDiagnosis,
                result: RetrievalResult, meta: Meta) -> DiagnosisResponse:
        refs = {s.ref.id: s.ref for s in sources}

        def cite(ids: list[str]) -> list[Citation]:
            return [Citation(source_id=i, manual=refs[i].manual, manual_title=refs[i].manual_title, page=refs[i].page_start)
                    for i in dict.fromkeys(ids)]

        # The LLM's confidence is a ranking signal; without an exact code it cannot exceed retrieval strength.
        cap = 1.0 if result.matched_codes else max(result.top_score, 0.0)
        causes = [Cause(rank=n, cause=c.cause, confidence=round(min(max(c.confidence, 0.0), 1.0, cap), 2),
                        fault_code=c.fault_code or None, citations=cite(c.source_ids))
                  for n, c in enumerate(parsed.probable_causes, 1)]
        steps = [Step(step=n, action=s.action, requires_isolation=s.requires_isolation, citations=cite(s.source_ids))
                 for n, s in enumerate(parsed.corrective_actions, 1)]
        warnings = [SafetyWarning(text=w.text, citations=cite(w.source_ids)) for w in parsed.safety_warnings]
        return DiagnosisResponse(
            status="diagnosis", query=query, machine_id=machine_id, language=language, matched_fault_codes=matched,
            probable_causes=causes, corrective_actions=steps, safety_warnings=warnings, escalation=None,
            sources=[s.ref for s in sources], meta=meta,
        )

    def _escalation(self, query, machine_id, language, matched, sources, reason: str, meta: Meta) -> DiagnosisResponse:
        codes = ", ".join(f"{m.code} ({m.manual})" for m in matched)
        summary = (f'Operator report: "{query}". Machine: {machine_id or "not specified"}.'
                   + (f" Fault code(s) recognised: {codes}." if codes else "")
                   + f" {reason} Escalate to a maintenance engineer; no cause was guessed.")
        considered = [s.ref for s in sources if s.ref.kind != "safety"][:3]
        return DiagnosisResponse(
            status="escalate", query=query, machine_id=machine_id, language=language, matched_fault_codes=matched,
            probable_causes=[], corrective_actions=[], safety_warnings=[],
            escalation=Escalation(reason=reason, summary=summary, sources_considered=considered,
                                  collect=list(COLLECT_CHECKLIST)),
            sources=[s.ref for s in sources], meta=meta,
        )

    def _finish(self, response: DiagnosisResponse, started: float, language: str) -> DiagnosisResponse:
        response.meta.latency_ms = int((self._clock() - started) * 1000)
        return self._language.from_english(response, language)
