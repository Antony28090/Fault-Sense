"""Grounding checks on the LLM's answer: citations, identifiers and safety."""
from __future__ import annotations

import re
from dataclasses import dataclass

from faultsense.codes import LABEL_RE, bracket_labels, code_key, code_like_tokens, confusable_variants, label_key
from faultsense.diagnosis.schema import LLMDiagnosis

# Generic electrical terms that are not Altivar identifiers.
GENERIC_TERMS = frozenset({
    "AC", "DC", "PE", "EMC", "IGBT", "HMI", "PID", "PLC", "VFD", "LOTO", "PPE", "OK", "LED", "USB",
    "PC", "RMS", "UL", "IEC", "CSA", "CPU", "ID",
})
_SOURCE_ID_RE = re.compile(r"^S\d{1,2}$")


@dataclass(frozen=True)
class KnownIdentifiers:
    codes: frozenset[str]  # code keys of every fault code, HMI code and code-like token in the manuals
    labels: frozenset[str]  # label keys of every bracketed menu/parameter name

    def knows_code(self, token: str) -> bool:
        key = code_key(token)
        return key in self.codes or bool(confusable_variants(key) & self.codes)

    def knows_label(self, label: str) -> bool:
        return label_key(label) in self.labels


def unknown_identifiers(text: str, known: KnownIdentifiers) -> list[str]:
    """Bracketed names and code-like tokens in `text` that appear nowhere in the manuals."""
    found = [f"[{label}]" for label in bracket_labels(text) if not known.knows_label(label)]
    for token in code_like_tokens(LABEL_RE.sub(" ", text)):
        if token.upper() in GENERIC_TERMS or _SOURCE_ID_RE.match(token):
            continue
        if not known.knows_code(token):
            found.append(token)
    return list(dict.fromkeys(found))


def _citations(label: str, ids: list[str], valid: set[str]) -> list[str]:
    if not ids:
        return [f"{label}: no citation"]
    return [f"{label}: unknown source id {i}" for i in ids if i not in valid]


def check_llm_output(out: LLMDiagnosis, valid_ids: set[str], safety_ids: set[str],
                     known: KnownIdentifiers) -> list[str]:
    if out.status == "insufficient_evidence":
        return []
    violations: list[str] = []
    if not out.probable_causes:
        violations.append("no probable causes returned")
    for n, cause in enumerate(out.probable_causes, 1):
        violations += _citations(f"cause {n}", cause.source_ids, valid_ids)
        violations += [f"cause {n}: unknown identifier {x}" for x in unknown_identifiers(cause.cause, known)]
        if cause.fault_code and not known.knows_code(cause.fault_code):
            violations.append(f"cause {n}: unknown identifier {cause.fault_code}")
    for n, step in enumerate(out.corrective_actions, 1):
        violations += _citations(f"step {n}", step.source_ids, valid_ids)
        violations += [f"step {n}: unknown identifier {x}" for x in unknown_identifiers(step.action, known)]
    for n, warning in enumerate(out.safety_warnings, 1):
        violations += _citations(f"safety warning {n}", warning.source_ids, valid_ids)
        violations += [f"safety warning {n}: unknown identifier {x}" for x in unknown_identifiers(warning.text, known)]
    needs_isolation = any(step.requires_isolation for step in out.corrective_actions)
    if needs_isolation and not any(set(w.source_ids) & safety_ids for w in out.safety_warnings):
        violations.append("steps require isolation but no safety warning cites a safety source")
    return violations
