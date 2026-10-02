"""Every identifier the manuals contain: fault codes, HMI codes (code font), code-like tokens
and bracketed menu/parameter labels. Answers may only use identifiers found here."""
from __future__ import annotations

import re
from dataclasses import dataclass

from faultsense.codes import TOKEN_RE, bracket_labels, code_key, code_like_tokens, label_key
from faultsense.ingest.faults import FaultRecord
from faultsense.ingest.pdf_reader import PdfDocument

_TRAILING_LABEL_RE = re.compile(r"\[([^\[\]]+)\]\s*$")


@dataclass(frozen=True)
class LexiconEntry:
    manual_id: str
    kind: str  # fault | hmi | token | label
    code: str
    code_key: str
    label: str | None
    first_page: int


def build_lexicon(doc: PdfDocument, manual_id: str, faults: list[FaultRecord]) -> list[LexiconEntry]:
    entries: dict[tuple[str, str], LexiconEntry] = {}

    def add(kind: str, code: str, key: str, label: str | None, page: int) -> None:
        if key and (kind, key) not in entries:
            entries[(kind, key)] = LexiconEntry(manual_id, kind, code, key, label, page)

    for record in faults:
        add("fault", record.code, record.code_key, record.name, record.page)
        # Fault names are real identifiers even where the manual prints them unbracketed (ATV12 table cells).
        add("label", record.name, label_key(record.name), None, record.page)
    for page in doc.pages:
        for line in page.lines:
            for i, span in enumerate(line.spans):
                if not span.is_code_font:
                    continue
                label = None
                if i > 0:
                    match = _TRAILING_LABEL_RE.search(line.spans[i - 1].text)
                    label = match.group(1).strip() if match else None
                for token in TOKEN_RE.findall(span.text):
                    add("hmi", token, code_key(token), label, page.number)
            for token in code_like_tokens(line.text):
                add("token", token, code_key(token), None, page.number)
            for text in bracket_labels(line.text):
                add("label", text, label_key(text), None, page.number)
    return list(entries.values())
