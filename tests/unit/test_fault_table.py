from faultsense.ingest.fault_table import code_from_cell, rows_to_records

HEADER = ["Code", "Name", "Possible causes", "Remedy"]


def test_rows_become_records_with_bullets_and_wrapping():
    rows = [
        HEADER,
        ["OCF", "Overcurrent", "• Inertia or load too high\n• Mechanical locking",
         "• Check the parameters\n• Reduce the Switching frequency SFr\npage 62"],
        ["", None, None, None],
    ]
    records, rejected, notes, _ = rows_to_records(rows, "atv12", 112, "Fault detection codes that cannot be cleared automatically")
    assert [r.code for r in records] == ["OCF"]
    assert records[0].causes == ["Inertia or load too high", "Mechanical locking"]
    assert records[0].remedies == ["Check the parameters", "Reduce the Switching frequency SFr page 62"]
    assert records[0].clearing.startswith("Fault detection codes")
    assert rejected == []
    assert notes == ["p112: blank table row skipped"]


def test_merged_cells_are_shared_with_the_previous_row():
    rows = [
        HEADER,
        ["SCF1", "Motor or Ground short circuit", "• Short-circuit at drive output", "• Check the cables"],
        ["SCF3", "Ground short circuit", None, None],
    ]
    (scf1, scf3), rejected, _, _ = rows_to_records(rows, "atv12", 112, "x")
    assert scf3.causes == scf1.causes and scf3.remedies == scf1.remedies
    assert scf3.shared_with == ["SCF1"] and scf1.shared_with == ["SCF3"]
    assert rejected == []


def test_footnote_markers_and_merged_header_cells():
    rows = [["Code Name", None, "Possible causes", "Remedy"],
            ["CFI\n(1)", "Invalid configuration", "• Invalid configuration", "• Check the configuration"]]
    records, *_ = rows_to_records(rows, "atv12", 115, "x")
    assert [r.code for r in records] == ["CFI"]
    assert code_from_cell("COM.E\n(1)") == "COM.E"


def test_unreadable_code_and_missing_remedy_are_rejected_not_skipped():
    rows = [HEADER, ["??", "Mystery", "• cause", "• fix"], ["OHF", "Drive overheat", "• Drive temperature too high", ""]]
    records, rejected, _, _ = rows_to_records(rows, "atv12", 113, "x")
    assert records == []
    assert [row.reason for row in rejected] == ["unreadable code cell", "no remedy"]


def test_three_column_table_has_no_remedies_and_a_note():
    rows = [["Code", "Name", "Description"], ["COM.E\n(1)", "Communication error", "• It has 50ms time-out error."]]
    records, rejected, notes, _ = rows_to_records(rows, "atv12", 116, "x")
    assert records[0].code == "COM.E" and records[0].remedies == []
    assert rejected == [] and "no remedy column" in notes[0]
