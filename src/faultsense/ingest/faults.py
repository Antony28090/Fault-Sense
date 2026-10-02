"""Fault records shared by both parsers, plus bullet/paragraph item assembly."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from faultsense.codes import code_key

CODE_OK_RE = re.compile(r"[A-Z0-9][A-Z0-9.\-]{1,6}|-{2,4}")
_BULLET_RE = re.compile(r"^[•●▪]\s*")


@dataclass
class FaultRecord:
    manual_id: str
    code: str  # as printed: 'InFI', 'blF', 'OHF'
    name: str
    description: str
    causes: list[str]
    remedies: list[str]
    clearing: str
    page: int
    page_end: int
    layout: str  # block | table4
    shared_with: list[str] = field(default_factory=list)

    @property
    def code_key(self) -> str:
        return code_key(self.code)


@dataclass(frozen=True)
class RejectedRow:
    page: int
    reason: str
    raw: str


@dataclass
class ParseResult:
    records: list[FaultRecord]
    rejected: list[RejectedRow]
    consumed: set[tuple[int, int]]  # line ids now owned by fault records (excluded from sections)
    notes: list[str] = field(default_factory=list)


def assemble_items(lines: list[str]) -> list[str]:
    """Join wrapped lines into items. A bullet starts an item; a capitalised line after a line
    ending in sentence punctuation starts a new paragraph item; anything else continues."""
    items: list[str] = []
    current: str | None = None
    for raw in lines:
        text = raw.strip()
        if not text:
            continue
        if _BULLET_RE.match(text):
            if current:
                items.append(current)
            current = _BULLET_RE.sub("", text)
            continue
        if not current:
            current = text
        elif current.rstrip().endswith((".", ":", "!", "?")) and text[:1].isupper():
            items.append(current)
            current = text
        else:
            current = f"{current} {text}"
    if current:
        items.append(current)
    return [re.sub(r"\s+", " ", item).strip() for item in items if item.strip()]


def fault_chunk_id(record: FaultRecord) -> str:
    return f"{record.manual_id}:f:{record.code_key}"


def fault_chunk_text(record: FaultRecord) -> str:
    lines = [f"Fault code {record.code}: {record.name}"]
    if record.description and record.description.lower() != record.name.lower():
        lines.append(record.description)
    lines.append("Probable causes:")
    lines += [f"- {cause}" for cause in record.causes]
    if record.remedies:
        lines.append("Remedies:")
        lines += [f"- {remedy}" for remedy in record.remedies]
    if record.clearing:
        lines.append(f"Clearing: {record.clearing}")
    if record.shared_with:
        lines.append("Same causes and remedies as: " + ", ".join(record.shared_with))
    return "\n".join(lines)


def dedupe(records: list[FaultRecord]) -> tuple[list[FaultRecord], list[str]]:
    seen: dict[str, FaultRecord] = {}
    duplicates: list[str] = []
    for record in records:
        first = seen.get(record.code_key)
        if first is None:
            seen[record.code_key] = record
        else:
            duplicates.append(f"{record.code} (p{record.page}, first seen p{first.page})")
    return list(seen.values()), duplicates
