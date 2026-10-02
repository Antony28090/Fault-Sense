"""PDF -> sections + fault records + lexicon + report, with no database involved."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from faultsense.fetch import sha256_file
from faultsense.ingest.fault_block import parse_block_faults
from faultsense.ingest.fault_table import parse_table_faults
from faultsense.ingest.faults import FaultRecord, ParseResult, dedupe, fault_chunk_id, fault_chunk_text
from faultsense.ingest.lexicon import LexiconEntry, build_lexicon
from faultsense.ingest.pdf_reader import PdfDocument, read_pdf
from faultsense.ingest.report import ManualReport, build_report
from faultsense.ingest.sectioner import Chunk, build_section_chunks
from faultsense.manifest import ManualSpec


@dataclass
class ExtractedManual:
    spec: ManualSpec
    sha256: str
    page_count: int
    chunks: list[Chunk]
    faults: list[FaultRecord]
    lexicon: list[LexiconEntry]
    report: ManualReport | None = None


def parse_faults(doc: PdfDocument, spec: ManualSpec) -> ParseResult:
    if spec.fault_layout == "block":
        return parse_block_faults(doc, spec.id, *spec.fault_pages)
    return parse_table_faults(doc, spec.id, *spec.fault_pages)


def fault_chunks(faults: list[FaultRecord]) -> list[Chunk]:
    return [
        Chunk(fault_chunk_id(r), r.manual_id, "fault", f"Error codes > {r.code} [{r.name}]",
              r.page, r.page_end, fault_chunk_text(r))
        for r in faults
    ]


def extract_manual(spec: ManualSpec, manuals_dir: Path) -> ExtractedManual:
    path = spec.path(manuals_dir)
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing: run `faultsense fetch-manuals`")
    doc = read_pdf(path)
    parsed = parse_faults(doc, spec)
    faults, duplicates = dedupe(parsed.records)
    sections = build_section_chunks(doc, spec.id, exclude=parsed.consumed, safety_pages=set(spec.safety_pages))
    report = build_report(doc, spec, parsed, faults, duplicates, sections)
    return ExtractedManual(
        spec=spec, sha256=sha256_file(path), page_count=doc.page_count,
        chunks=sections.chunks + fault_chunks(faults), faults=faults,
        lexicon=build_lexicon(doc, spec.id, faults), report=report,
    )


def save_extraction(ex: ExtractedManual, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for chunk in ex.chunks:
        counts[chunk.kind] = counts.get(chunk.kind, 0) + 1
    data = {
        "manual": ex.spec.id,
        "sha256": ex.sha256,
        "page_count": ex.page_count,
        "chunk_counts": counts,
        "faults": [asdict(f) | {"code_key": f.code_key} for f in ex.faults],
        "report": asdict(ex.report) if ex.report else None,
    }
    path = out_dir / f"{ex.spec.id}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def write_report_file(extracted: list[ExtractedManual], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {ex.spec.id: asdict(ex.report) | {"problems": ex.report.problems} for ex in extracted if ex.report}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
