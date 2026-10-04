"""Grounding checks on the LLM's answer: citations, identifiers and safety."""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cached_property

from faultsense.codes import (LABEL_RE, bare_code, bracket_labels, code_key, code_like_tokens, confusable_variants,
                             label_key)
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
        key = label_key(label)
        return key in self.labels or _loose(key) in self._loose_labels

    @cached_property
    def _loose_labels(self) -> frozenset[str]:
        return frozenset(_loose(key) for key in self.labels)


def _loose(key: str) -> str:
    # Some manual names join words with underscores ([BRH_b4_freq]); answers often write spaces instead.
    return re.sub(r"[\s_]+", " ", key).strip()


def _same_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" .;:!").lower()


def unknown_identifiers(text: str, known: KnownIdentifiers) -> list[str]:
    """Bracketed names and code-like tokens in `text` that appear nowhere in the manuals."""
    found = [f"[{label}]" for label in bracket_labels(text) if not known.knows_label(label)]
    for token in code_like_tokens(LABEL_RE.sub(" ", text)):
        if _SOURCE_ID_RE.match(token):
            continue
        # A plural with a lowercase "s" (IDs, PLCs, OHFs) is the term or code itself.
        forms = [token] + ([token[:-1]] if len(token) > 2 and token.endswith("s") else [])
        if not any(form.upper() in GENERIC_TERMS or known.knows_code(form) for form in forms):
            found.append(token)
    return list(dict.fromkeys(found))


def _fault_code_unknowns(fault_code: str, known: KnownIdentifiers) -> list[str]:
    """The code field may carry the manual's name as well ("[Autotuning Error] TNF"); both must be known."""
    found = [f"[{label}]" for label in bracket_labels(fault_code) if not known.knows_label(label)]
    code = bare_code(fault_code)
    if code and not known.knows_code(code):
        found.append(code)
    return found


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
    seen: dict[str, int] = {}
    for n, cause in enumerate(out.probable_causes, 1):
        violations += _citations(f"cause {n}", cause.source_ids, valid_ids)
        violations += [f"cause {n}: unknown identifier {x}" for x in unknown_identifiers(cause.cause, known)]
        if cause.fault_code:
            violations += [f"cause {n}: unknown identifier {x}" for x in _fault_code_unknowns(cause.fault_code, known)]
        first = seen.setdefault(_same_text(cause.cause), n)
        if first != n:
            violations.append(f"cause {n} repeats cause {first}: list each cause once")
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
