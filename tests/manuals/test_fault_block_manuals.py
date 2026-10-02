import pytest

from faultsense.ingest.fault_block import parse_block_faults

pytestmark = pytest.mark.manuals


@pytest.mark.parametrize("manual_id,count", [("atv320", 60), ("atv600", 134), ("atv900", 147)])
def test_block_record_counts(manual_doc, manual_id, count):
    spec, doc = manual_doc(manual_id)
    result = parse_block_faults(doc, manual_id, *spec.fault_pages)
    assert len(result.records) == count
    assert all(r.causes and r.remedies for r in result.records)


def test_atv600_ohf_record(manual_doc):
    spec, doc = manual_doc("atv600")
    ohf = {r.code: r for r in parse_block_faults(doc, "atv600", *spec.fault_pages).records}["OHF"]
    assert (ohf.name, ohf.page) == ("Device Overheat", 672)
    assert "Ambient temperature too high." in ohf.causes
    assert "Clean the heat sink." in ohf.remedies


def test_atv900_rotation_angle_heading_is_reported(manual_doc):
    spec, doc = manual_doc("atv900")
    result = parse_block_faults(doc, "atv900", *spec.fault_pages)
    assert any(row.page == 684 and "Rotation Angle Monit" in row.raw for row in result.rejected)


def test_atv320_codes_kept_as_printed(manual_doc):
    spec, doc = manual_doc("atv320")
    codes = {r.code for r in parse_block_faults(doc, "atv320", *spec.fault_pages).records}
    assert {"blF", "phf", "tnf", "SCFS"} <= codes
