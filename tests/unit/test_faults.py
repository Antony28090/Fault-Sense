from faultsense.ingest.faults import FaultRecord, assemble_items, dedupe, fault_chunk_id, fault_chunk_text


def test_assemble_items_handles_bullet_lines_and_wrapping():
    lines = [
        "Device temperature too high.", "•", "Ambient temperature too high.", "•",
        "Reduced air flow due to blocked air at the inlet or", "outlet.",
        "Wait for the device to cool down before restarting.",
    ]
    assert assemble_items(lines) == [
        "Device temperature too high.",
        "Ambient temperature too high.",
        "Reduced air flow due to blocked air at the inlet or outlet.",
        "Wait for the device to cool down before restarting.",
    ]


def test_assemble_items_inline_bullets_and_lowercase_continuation():
    lines = ["• Charging relay control fault or", "charging resistor damaged", "• Check the connections"]
    assert assemble_items(lines) == [
        "Charging relay control fault or charging resistor damaged",
        "Check the connections",
    ]


def _record(code="OHF", page=10):
    return FaultRecord("m1", code, "Device Overheat", "Device overheating", ["Ambient too hot."],
                       ["Verify the fans."], "Auto reset.", page, page, "block")


def test_chunk_id_and_text():
    record = _record()
    assert fault_chunk_id(record) == "m1:f:OHF"
    text = fault_chunk_text(record)
    assert text.startswith("Fault code OHF: Device Overheat")
    assert "- Ambient too hot." in text and "- Verify the fans." in text
    assert "Clearing: Auto reset." in text


def test_dedupe_keeps_first_and_reports_duplicates():
    records, duplicates = dedupe([_record(page=10), _record(code="ohf", page=12)])
    assert [r.page for r in records] == [10]
    assert duplicates == ["ohf (p12, first seen p10)"]
