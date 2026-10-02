"""Extraction report: everything a human must look at before trusting the extracted data."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from faultsense.codes import code_key, confusable_variants
from faultsense.ingest.faults import FaultRecord, ParseResult, RejectedRow
from faultsense.ingest.pdf_reader import PdfDocument
from faultsense.ingest.sectioner import SectionResult
from faultsense.manifest import ManualSpec

INDEX_RE = re.compile(
    r"^\[(?P<name>[^\]]+)\]\s+(?P<code>[A-Za-z0-9][A-Za-z0-9.\-]*?)\s*\.{2,}\s*(?P<page>\d+)\s*$"
)
LEADER_RE = re.compile(r"\.{5,}\s*\d+\s*$")
_HEADING_LIKE_RE = re.compile(r"^\[[^\]]+\]\s+(\S{2,6})$")


@dataclass
class ManualReport:
    manual_id: str
    fault_records: int = 0
    section_chunks: int = 0
    safety_chunks: int = 0
    rejected: list[RejectedRow] = field(default_factory=list)
    missing_from_extraction: list[str] = field(default_factory=list)
    unparsed_index_lines: list[str] = field(default_factory=list)
    duplicate_codes: list[str] = field(default_factory=list)
    confusable_pairs: list[str] = field(default_factory=list)  # information only
    page_number_mismatches: list[str] = field(default_factory=list)
    toc_titles_not_found: list[str] = field(default_factory=list)  # information only
    notes: list[str] = field(default_factory=list)  # information only

    @property
    def problems(self) -> list[str]:
        found = []
        if self.rejected:
            found.append(f"{len(self.rejected)} rejected fault rows")
        if self.missing_from_extraction:
            found.append(f"{len(self.missing_from_extraction)} codes expected but not extracted")
        if self.unparsed_index_lines:
            found.append(f"{len(self.unparsed_index_lines)} unparsed index lines")
        if self.duplicate_codes:
            found.append(f"{len(self.duplicate_codes)} duplicate codes")
        if self.page_number_mismatches:
            found.append(f"{len(self.page_number_mismatches)} printed page numbers differ from PDF pages")
        if self.safety_chunks == 0:
            found.append("no safety chunk on the configured safety pages")
        return found


def chapter_index(doc: PdfDocument, first: int, last: int) -> tuple[dict[str, str], list[str]]:
    """Codes listed in a chapter's '[Name] CODE .... page' index, plus leader lines that did not parse."""
    found: dict[str, str] = {}
    unparsed: list[str] = []
    for line in doc.iter_lines(first, last):
        match = INDEX_RE.match(line.text)
        if match:
            found[code_key(match["code"])] = match["code"]
        elif LEADER_RE.search(line.text) and not line.text.startswith("Overview"):
            unparsed.append(f"p{line.page}: {line.text}")
    return found, unparsed


def _table_code_column(doc: PdfDocument, consumed: set[tuple[int, int]]) -> dict[str, str]:
    """Code-font cells at the left edge of the parsed tables."""
    found: dict[str, str] = {}
    for page_number in sorted({page for page, _ in consumed}):
        page = doc.page(page_number)
        for line in page.lines:
            if line.id in consumed and line.bbox[0] < page.width * 0.2 and line.spans[0].is_code_font:
                key = code_key(line.spans[0].text)
                if key:
                    found[key] = line.spans[0].text.strip()
    return found


def _heading_like(doc: PdfDocument, first: int, last: int) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in doc.iter_lines(first, last):
        match = _HEADING_LIKE_RE.match(line.text)
        if match and line.spans[0].bold and line.spans[0].size >= 15:
            found[code_key(match.group(1))] = match.group(1)
    return found


def build_report(
    doc: PdfDocument,
    spec: ManualSpec,
    parsed: ParseResult,
    faults: list[FaultRecord],
    duplicates: list[str],
    sections: SectionResult,
) -> ManualReport:
    report = ManualReport(
        manual_id=spec.id,
        fault_records=len(faults),
        section_chunks=sum(c.kind == "section" for c in sections.chunks),
        safety_chunks=sum(c.kind == "safety" for c in sections.chunks),
        rejected=list(parsed.rejected),
        duplicate_codes=list(duplicates),
        page_number_mismatches=[f"pdf p{pdf} prints {printed}" for pdf, printed in doc.page_mismatches()],
        toc_titles_not_found=list(sections.titles_not_found),
        notes=list(parsed.notes),
    )
    if spec.index_pages:
        expected, report.unparsed_index_lines = chapter_index(doc, *spec.index_pages)
    elif spec.fault_layout == "table4":
        expected = _table_code_column(doc, parsed.consumed)
    else:
        expected = _heading_like(doc, *spec.fault_pages)
    extracted = {record.code_key for record in faults}
    report.missing_from_extraction = sorted(expected[key] for key in expected.keys() - extracted)
    report.confusable_pairs = sorted({
        f"{a}~{b}" for a in extracted for b in confusable_variants(a) if b in extracted and a < b
    })
    return report
