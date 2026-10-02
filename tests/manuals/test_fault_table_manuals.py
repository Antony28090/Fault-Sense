import pytest

from faultsense.ingest.fault_table import parse_table_faults

pytestmark = pytest.mark.manuals


def test_atv12_fault_tables(manual_doc):
    spec, doc = manual_doc("atv12")
    result = parse_table_faults(doc, "atv12", *spec.fault_pages)
    by_code = {r.code: r for r in result.records}
    assert len(result.records) == 44
    assert result.rejected == []
    assert by_code["SCF3"].causes == by_code["SCF1"].causes
    assert by_code["InFI"].page == 111
    assert by_code["OHF"].page == 113
    assert by_code["OHF"].causes[0].startswith("Drive temperature too high")
    assert {"CFI", "COM.E", "----"} <= set(by_code)
    assert result.consumed
