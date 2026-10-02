from helpers import make_doc
from faultsense.ingest.faults import FaultRecord, ParseResult
from faultsense.ingest.report import build_report, chapter_index
from faultsense.ingest.sectioner import Chunk, SectionResult
from faultsense.manifest import ManualSpec


def _spec(**overrides):
    base = dict(id="m1", family="ATVX", title="T", doc_ref="D", version="01", file="m1.pdf",
                url="https://example.invalid", sha256="0" * 64, fault_layout="block",
                fault_pages=(2, 2), index_pages=(1, 1), safety_pages=[1])
    return ManualSpec(**(base | overrides))


def test_chapter_index_parses_entries_and_reports_broken_lines():
    doc = make_doc({1: [
        "Overview.......................643",
        "[Overcurrent] OCF ........ 672",
        "[Device Overheat] OHF......672",
        "[Rotation Angle Monit]",
        "RAMF ............ 684",
    ]})
    found, unparsed = chapter_index(doc, 1, 1)
    assert found == {"OCF": "OCF", "OHF": "OHF"}
    assert unparsed == ["p1: RAMF ............ 684"]


def test_report_lists_codes_missing_from_extraction():
    doc = make_doc({1: ["[Overcurrent] OCF ........ 2", "[Device Overheat] OHF ........ 2"], 2: []})
    ocf = FaultRecord("m1", "OCF", "Overcurrent", "", ["c"], ["r"], "", 2, 2, "block")
    parsed = ParseResult([ocf], [], set())
    sections = SectionResult([Chunk("m1:s00000", "m1", "safety", "Safety", 1, 1, "Disconnect all power")])
    report = build_report(doc, _spec(), parsed, [ocf], [], sections)
    assert report.missing_from_extraction == ["OHF"]
    assert report.safety_chunks == 1
    assert report.problems == ["1 codes expected but not extracted"]


def test_missing_safety_chunk_is_a_problem():
    doc = make_doc({1: [], 2: []})
    report = build_report(doc, _spec(index_pages=None), ParseResult([], [], set()), [], [], SectionResult([]))
    assert "no safety chunk on the configured safety pages" in report.problems


def test_lookalike_pairs_are_listed_as_information():
    doc = make_doc({1: [], 2: []})
    records = [FaultRecord("m1", code, "n", "", ["c"], ["r"], "", 2, 2, "block") for code in ("INF1", "INFI")]
    sections = SectionResult([Chunk("m1:s00000", "m1", "safety", "S", 1, 1, "x")])
    report = build_report(doc, _spec(index_pages=None), ParseResult(records, [], set()), records, [], sections)
    assert report.confusable_pairs == ["INF1~INFI"]
    assert report.problems == []
