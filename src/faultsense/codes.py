"""Fault-code keys, 7-segment look-alikes and identifier tokens.

Altivar displays render O/0, I/1 and S/5 identically, and the manuals themselves mix them
(ATV12 prints `InFI`, ATV320 prints `SCFS` for `SCF5`). Keys therefore stay exact; look-alikes
are generated separately so callers can try them only where no exact match exists.
"""
from __future__ import annotations

import re
from itertools import product

_LOOKALIKES = {"O": "0", "0": "O", "I": "1", "1": "I", "S": "5", "5": "S"}
_FOOTNOTE_RE = re.compile(r"\(\d+\)")

TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[.\-][A-Za-z0-9]+)*")
LABEL_RE = re.compile(r"\[([^\[\]\n]{2,60})\]")


def code_key(code: str) -> str:
    """Case-insensitive comparison key: ' InFI (1)' -> 'INFI', 'DRC–' -> 'DRC', '----' stays."""
    text = re.sub(r"\s+", "", _FOOTNOTE_RE.sub("", code))
    if re.search(r"[A-Za-z0-9]", text):
        text = text.rstrip("-–—")
    return text.upper()


def confusable_variants(key: str, limit: int = 64) -> set[str]:
    """Other keys that look identical on a 7-segment display (O/0, I/1, S/5)."""
    options = [(ch, _LOOKALIKES[ch]) if ch in _LOOKALIKES else (ch,) for ch in key]
    variants: set[str] = set()
    for combo in product(*options):
        variants.add("".join(combo))
        if len(variants) >= limit:
            break
    variants.discard(key)
    return variants


def is_code_like(token: str) -> bool:
    """True for tokens shaped like HMI codes (OHF, SCF1, tFr, blF, kW); False for words."""
    if len(token) < 2 or not any(ch.isalpha() for ch in token):
        return False
    uppers = sum(ch.isupper() for ch in token)
    has_digit = any(ch.isdigit() for ch in token)
    if uppers >= 2:
        return True
    if uppers == 1 and not token[0].isupper():
        return True
    return has_digit and uppers >= 1


def code_like_tokens(text: str) -> list[str]:
    return [tok for tok in TOKEN_RE.findall(text) if is_code_like(tok)]


def bracket_labels(text: str) -> list[str]:
    return [match.strip() for match in LABEL_RE.findall(text)]


def label_key(label: str) -> str:
    return re.sub(r"\s+", " ", label.strip().strip("[]").strip()).lower()


def query_code_candidates(text: str) -> list[str]:
    """Tokens an operator may have typed as a fault code: 3-6 chars with at least one letter.

    Also tries the parts of hyphen-joined tokens ("OHF-fault" -> "OHF") and a short code followed by
    a separate digit ("SCF 1" -> "SCF1"); dotted and hyphenated codes such as COM.E and A-17 stay whole.
    """
    tokens = TOKEN_RE.findall(text)
    candidates: list[str] = []
    for i, tok in enumerate(tokens):
        candidates.append(tok)
        if "-" in tok:
            candidates.extend(tok.split("-"))
        following = tokens[i + 1] if i + 1 < len(tokens) else ""
        if tok.isalpha() and 2 <= len(tok) <= 4 and following.isdigit() and len(following) <= 2:
            candidates.append(tok + following)
    return [
        tok for tok in dict.fromkeys(candidates)
        if 3 <= len(tok) <= 6 and any(ch.isalpha() for ch in tok)
    ]
