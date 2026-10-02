"""ATV12-style ruled fault tables: Code | Name | Possible causes | Remedy.

Tables continue across pages under "(continued)" headings, repeat their header row, merge the
cause/remedy cells of consecutive codes (SCF1/SCF3) and carry footnote markers such as "(1)".
"""
from __future__ import annotations

import re

import pymupdf

from faultsense.codes import code_key
from faultsense.ingest.faults import CODE_OK_RE, FaultRecord, ParseResult, RejectedRow, assemble_items
from faultsense.ingest.pdf_reader import PdfDocument

_FOOTNOTE_RE = re.compile(r"\(\d+\)")
_CONTINUED_RE = re.compile(r"\s*\(continued\)\s*$", re.IGNORECASE)


def code_from_cell(cell: str | None) -> str:
    tokens = _FOOTNOTE_RE.sub(" ", cell or "").split()
    return tokens[0] if tokens else ""


def _join(cell: str | None) -> str:
    return re.sub(r"\s+", " ", cell or "").strip()


def rows_to_records(rows, manual_id: str, page: int, clearing: str, prev: FaultRecord | None = None):
    """Returns (records, rejected rows, notes, last record) for one extracted table."""
    records: list[FaultRecord] = []
    rejected: list[RejectedRow] = []
    notes: list[str] = []
    width = max((len(row) for row in rows), default=0)
    for raw in rows:
        cells = list(raw) + [None] * (width - len(raw))
        first = (cells[0] or "").strip()
        if first.lower().startswith("code"):
            continue  # header row, repeated on every page
        if not any((cell or "").strip() for cell in cells):
            notes.append(f"p{page}: blank table row skipped")
            continue
        code = code_from_cell(first)
        name = _join(cells[1]) if width > 1 else ""
        shared: list[str] = []
        if width >= 4 and cells[2] is None and cells[3] is None and prev is not None:
            causes, remedies = list(prev.causes), list(prev.remedies)  # merged cell
            shared = [prev.code]
            prev.shared_with.append(code)
        else:
            causes = assemble_items((cells[2] or "").splitlines()) if width > 2 else []
            remedies = assemble_items((cells[3] or "").splitlines()) if width >= 4 else []
        raw_text = " | ".join(_join(cell) for cell in cells)
        if not CODE_OK_RE.fullmatch(code_key(code)):
            rejected.append(RejectedRow(page, "unreadable code cell", raw_text))
            continue
        if not causes:
            rejected.append(RejectedRow(page, "no causes", raw_text))
            continue
        if width >= 4 and not remedies:
            rejected.append(RejectedRow(page, "no remedy", raw_text))
            continue
        if width < 4:
            notes.append(f"p{page}: {code} comes from a {width}-column table with no remedy column")
        record = FaultRecord(manual_id, code, name, "", causes, remedies, clearing, page, page, "table4", shared)
        records.append(record)
        prev = record
    return records, rejected, notes, prev


def _section_for_page(toc: list[tuple[int, str, int]], page: int) -> str:
    title = ""
    for _, entry, entry_page in toc:
        if entry_page <= page:
            title = entry
    return _CONTINUED_RE.sub("", title).strip()


def parse_table_faults(doc: PdfDocument, manual_id: str, first: int, last: int) -> ParseResult:
    result = ParseResult([], [], set())
    prev: FaultRecord | None = None
    with pymupdf.open(doc.path) as pdf:
        for number in range(first, last + 1):
            clearing = _section_for_page(doc.toc, number)
            for table in pdf[number - 1].find_tables().tables:
                records, rejected, notes, prev = rows_to_records(table.extract(), manual_id, number, clearing, prev)
                result.records.extend(records)
                result.rejected.extend(rejected)
                result.notes.extend(notes)
                x0, y0, x1, y1 = table.bbox
                for line in doc.page(number).lines:
                    cx = (line.bbox[0] + line.bbox[2]) / 2
                    cy = (line.bbox[1] + line.bbox[3]) / 2
                    if x0 <= cx <= x1 and y0 <= cy <= y1:
                        result.consumed.add(line.id)
    return result
