"""Drive model names in operator text, so FaultSense can tell which manual a question is about.

Recognises catalogue references ("ATV630D11N4" -> ATV630), short names ("atv 71", "ATV-312") and
spelled-out ranges ("Altivar Process 930" -> ATV930, "Altistart 48" -> ATS48). A bare number such as
"630 rpm" is never a model.
"""
from __future__ import annotations

import re

_NUMBER = r"(\d{2,3}|[69][AB]0)"
_PATTERNS = [
    (re.compile(rf"\b(ATV|ATS)[\s-]?{_NUMBER}", re.IGNORECASE), None),
    (re.compile(rf"\bAltivar\s+(?:Machine\s+|Process\s+|Easy\s+)?(?:ATV[\s-]?)?{_NUMBER}\b", re.IGNORECASE), "ATV"),
    (re.compile(rf"\bAltistart\s+(?:ATS[\s-]?)?{_NUMBER}\b", re.IGNORECASE), "ATS"),
]


def named_drive_models(text: str) -> list[str]:
    """Distinct drive models named in the text, normalised to e.g. "ATV630", in order of appearance."""
    found: list[tuple[int, str]] = []
    for pattern, prefix in _PATTERNS:
        for match in pattern.finditer(text):
            series, number = (prefix, match.group(1)) if prefix else (match.group(1), match.group(2))
            found.append((match.start(), f"{series}{number}".upper()))
    return list(dict.fromkeys(model for _, model in sorted(found)))
