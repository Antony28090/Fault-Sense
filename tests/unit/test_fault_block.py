from helpers import heading_spans, italic, make_doc, span
from faultsense.ingest.fault_block import parse_block_faults

PAGES = {
    10: [
        heading_spans("Overcurrent", "OCF"), italic("Overcurrent"),
        "Probable Cause", "•", "Inertia or load too high.",
        "Remedy", "•", "Verify the size of the motor/drive/load.",
        "Clearing the Error Code", "This detected error requires a power reset.",
        heading_spans("Device Overheat", "OHF"), italic("Device overheating"),
        "Probable Cause", "Ambient temperature too high.",
        "Remedy", "Verify the fans.",
    ],
    11: [
        "Clean the heat sink.", "Clearing the Error Code", "Cleared automatically.",
        [span("FAQ", "Arial-BoldMT", 19.9)], "Some FAQ text",
    ],
}


def test_blocks_become_records_across_page_breaks():
    result = parse_block_faults(make_doc(PAGES), "m1", 10, 11)
    ocf, ohf = result.records
    assert (ocf.code, ocf.name, ocf.description) == ("OCF", "Overcurrent", "Overcurrent")
    assert ocf.causes == ["Inertia or load too high."]
    assert ocf.remedies == ["Verify the size of the motor/drive/load."]
    assert ocf.clearing == "This detected error requires a power reset."
    assert (ohf.page, ohf.page_end) == (10, 11)
    assert ohf.remedies == ["Verify the fans.", "Clean the heat sink."]
    assert ohf.clearing == "Cleared automatically."
    assert result.rejected == []


def test_terminator_ends_the_last_block_and_is_not_consumed():
    doc = make_doc(PAGES)
    result = parse_block_faults(doc, "m1", 10, 11)
    faq_ids = {line.id for line in doc.page(11).lines[3:]}
    assert not faq_ids & result.consumed
    assert (10, 0) in result.consumed


def test_heading_without_code_font_is_reported_and_not_merged():
    pages = {5: [
        heading_spans("Overcurrent", "OCF"), "Probable Cause", "Load too high.", "Remedy", "Reduce load.",
        heading_spans("Rotation Angle Monit", "", code_font="ArialMT"),
        "Probable Cause", "Angle drift.", "Remedy", "Check encoder.",
    ]}
    result = parse_block_faults(make_doc(pages), "m1", 5, 5)
    assert [r.code for r in result.records] == ["OCF"]
    assert result.records[0].causes == ["Load too high."]
    assert result.rejected[0].reason == "heading-like line without a code-font code"
    assert "Rotation Angle Monit" in result.rejected[0].raw


def test_missing_remedy_is_rejected_and_lines_stay_unconsumed():
    pages = {5: [heading_spans("Odd", "ODF"), "Probable Cause", "Something."]}
    result = parse_block_faults(make_doc(pages), "m1", 5, 5)
    assert result.records == []
    assert result.rejected[0].reason == "no 'Remedy' content"
    assert result.consumed == set()
