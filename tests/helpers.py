"""Helpers shared by the test suites."""
from faultsense.config import PROJECT_ROOT
from faultsense.manifest import load_manuals

DATA_DIR = PROJECT_ROOT / "data"
MANUALS_DIR = DATA_DIR / "manuals"
SPECS = {spec.id: spec for spec in load_manuals(DATA_DIR / "manuals.yaml")}

from pathlib import Path

from faultsense.ingest.pdf_reader import Line, Page, PdfDocument, Span


def span(text: str, font: str = "ArialMT", size: float = 10.0) -> Span:
    return Span(text, font, size)


def make_line(page: int, index: int, content, y: float | None = None, x: float = 50.0) -> Line:
    """`content` is a plain string or a list of Spans."""
    spans = (span(content),) if isinstance(content, str) else tuple(content)
    top = 100.0 + 12.0 * index if y is None else y
    return Line(page, index, (x, top, x + 400.0, top + 10.0), spans)


def make_doc(pages: dict[int, list], toc=None, page_count: int | None = None) -> PdfDocument:
    count = page_count or max(pages)
    built = []
    for number in range(1, count + 1):
        lines = [make_line(number, i, item) for i, item in enumerate(pages.get(number, []))]
        built.append(Page(number, 595.0, 842.0, lines, number))
    return PdfDocument(Path("synthetic.pdf"), list(toc or []), built)


def heading_spans(name: str, code: str, code_font: str = "CourierNewPS-BoldMT", size: float = 17.9) -> list[Span]:
    return [span(f"[{name}]", "Arial-BoldMT", size), span(f" {code}", code_font, size)]


def italic(text: str, size: float = 15.9) -> list[Span]:
    return [span(text, "Arial-BoldItalicMT", size)]

from faultsense.ingest.extract import ExtractedManual
from faultsense.ingest.faults import FaultRecord, fault_chunk_id, fault_chunk_text
from faultsense.ingest.lexicon import LexiconEntry
from faultsense.ingest.sectioner import Chunk
from faultsense.manifest import ManualSpec


def sample_spec(manual_id: str = "m1") -> ManualSpec:
    return ManualSpec(
        id=manual_id, family="ATVX", title="Test Manual", doc_ref="DOC1", version="01", file="x.pdf",
        url="https://example.invalid/x.pdf", sha256="0" * 64, fault_layout="block",
        fault_pages=(10, 11), index_pages=None, safety_pages=[2],
    )


def sample_extracted(manual_id: str = "m1", sha: str = "a" * 64,
                     section_text: str = "Wiring the motor cables to the drive terminals.") -> ExtractedManual:
    fault = FaultRecord(manual_id, "OHF", "Drive Overheating", "Drive overheating",
                        ["Ambient temperature too high."], ["Verify the fans."], "Auto reset.", 10, 10, "block")
    chunks = [
        Chunk(f"{manual_id}:s00000", manual_id, "section", "Wiring", 5, 5, section_text),
        Chunk(fault_chunk_id(fault), manual_id, "fault", "Error codes > OHF [Drive Overheating]", 10, 10,
              fault_chunk_text(fault)),
        Chunk(f"{manual_id}:s00001", manual_id, "safety", "Safety Information", 2, 2,
              "DANGER: Disconnect all power. Wait 15 minutes. Measure the DC bus voltage."),
    ]
    lexicon = [
        LexiconEntry(manual_id, "fault", "OHF", "OHF", "Drive Overheating", 10),
        LexiconEntry(manual_id, "hmi", "CLI", "CLI", "Current Limitation", 50),
        LexiconEntry(manual_id, "label", "Current Limitation", "current limitation", None, 50),
    ]
    return ExtractedManual(sample_spec(manual_id), sha, 100, chunks, [fault], lexicon, None)
