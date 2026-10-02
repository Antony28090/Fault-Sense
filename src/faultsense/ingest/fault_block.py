"""Per-code fault blocks (ATV320/600/900):

    [Name] CODE              <- Arial-Bold >= 15 pt, code in the code font
    Italic description
    Probable Cause / Remedy / Clearing the Error Code   <- field labels
"""
from __future__ import annotations

from faultsense.codes import code_key
from faultsense.ingest.faults import CODE_OK_RE, FaultRecord, ParseResult, RejectedRow, assemble_items
from faultsense.ingest.pdf_reader import Line, PdfDocument

FIELD_LABELS = {"probable cause": "causes", "remedy": "remedies", "clearing the error code": "clearing"}
HEADING_MIN_SIZE = 15.0
TERMINATOR_MIN_SIZE = 17.0


def is_fault_heading(line: Line) -> bool:
    spans = line.spans
    return (
        len(spans) >= 2
        and spans[0].text.lstrip().startswith("[")
        and spans[0].bold
        and spans[0].size >= HEADING_MIN_SIZE
        and spans[1].is_code_font
    )


def is_terminator(line: Line) -> bool:
    """A chapter or section heading that is not a fault heading ends the current block."""
    first = line.spans[0]
    return first.bold and first.size >= TERMINATOR_MIN_SIZE and not is_fault_heading(line)


def _split_blocks(lines: list[Line]) -> tuple[list[list[Line]], list[RejectedRow]]:
    blocks: list[list[Line]] = []
    rejected: list[RejectedRow] = []
    current: list[Line] | None = None
    for line in lines:
        if is_fault_heading(line):
            if current:
                blocks.append(current)
            current = [line]
        elif is_terminator(line):
            if line.text.startswith("["):
                rejected.append(RejectedRow(line.page, "heading-like line without a code-font code", line.text))
            if current:
                blocks.append(current)
            current = None
        elif current is not None:
            current.append(line)
    if current:
        blocks.append(current)
    return blocks, rejected


def _record(block: list[Line], manual_id: str) -> FaultRecord | RejectedRow:
    heading = block[0]
    name = heading.spans[0].text.strip().strip("[]").strip()
    code = "".join(span.text for span in heading.spans[1:] if span.is_code_font).strip()
    description: list[str] = []
    fields: dict[str, list[str]] = {"causes": [], "remedies": [], "clearing": []}
    current: str | None = None
    for line in block[1:]:
        label = FIELD_LABELS.get(line.text.strip().lower())
        if label:
            current = label
        elif current is None:
            description.append(line.text)
        else:
            fields[current].append(line.text)
    record = FaultRecord(
        manual_id=manual_id, code=code, name=name, description=" ".join(description).strip(),
        causes=assemble_items(fields["causes"]), remedies=assemble_items(fields["remedies"]),
        clearing=" ".join(fields["clearing"]).strip(), page=heading.page, page_end=block[-1].page,
        layout="block",
    )
    problems = []
    if not CODE_OK_RE.fullmatch(code_key(code)):
        problems.append("unreadable code")
    if not record.causes:
        problems.append("no 'Probable Cause' content")
    if not record.remedies:
        problems.append("no 'Remedy' content")
    if problems:
        return RejectedRow(heading.page, "; ".join(problems), heading.text)
    return record


def parse_block_faults(doc: PdfDocument, manual_id: str, first: int, last: int) -> ParseResult:
    blocks, rejected = _split_blocks(list(doc.iter_lines(first, last)))
    records: list[FaultRecord] = []
    consumed: set[tuple[int, int]] = set()
    for block in blocks:
        outcome = _record(block, manual_id)
        if isinstance(outcome, RejectedRow):
            rejected.append(outcome)  # its lines stay available to the sectioner
        else:
            records.append(outcome)
            consumed.update(line.id for line in block)
    return ParseResult(records, rejected, consumed)
