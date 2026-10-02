from functools import lru_cache

import pytest

from helpers import MANUALS_DIR, SPECS
from faultsense.ingest.extract import extract_manual

pytestmark = pytest.mark.manuals


@lru_cache(maxsize=None)
def _extract(manual_id):
    spec = SPECS[manual_id]
    if not spec.path(MANUALS_DIR).exists():
        pytest.skip("run `faultsense fetch-manuals` first")
    return extract_manual(spec, MANUALS_DIR)


@pytest.mark.parametrize("manual_id,count", [("atv12", 44), ("atv320", 60), ("atv600", 134), ("atv900", 147)])
def test_counts_fault_chunks_and_safety(manual_id, count):
    ex = _extract(manual_id)
    assert len(ex.faults) == count
    assert sum(c.kind == "fault" for c in ex.chunks) == count
    assert ex.report.safety_chunks >= 1
    assert len({c.id for c in ex.chunks}) == len(ex.chunks)


def test_atv900_report_flags_the_rotation_angle_heading():
    report = _extract("atv900").report
    assert any("Rotation Angle Monit" in row.raw for row in report.rejected)
    assert report.problems
    assert "INF1~INFI" in report.confusable_pairs


def test_lexicon_knows_real_codes():
    keys = {(e.kind, e.code_key) for e in _extract("atv600").lexicon}
    assert ("fault", "OHF") in keys
    assert ("hmi", "CLI") in keys


# Hand-checked against the PDFs: (manual, code as printed, page, a cause substring or None).
GOLDEN = [
    ("atv12", "CrF1", 111, "Charging relay control fault"),
    ("atv12", "InFI", 111, "The power card is different"),
    ("atv12", "OCF", 112, "Inertia or load too high"),
    ("atv12", "SCF1", 112, "Short-circuit or grounding at the drive output"),
    ("atv12", "tnF", 112, "Motor not connected to the drive"),
    ("atv12", "OHF", 113, "Drive temperature too high"),
    ("atv12", "PHF", 114, None),
    ("atv12", "USF", 115, "Line supply too low"),
    ("atv320", "AsF", 404, "phase-shift angle measurement"),
    ("atv320", "blF", 404, "Brake release current not reached."),
    ("atv320", "brF", 405, "The brake feedback contact does not match the brake logic control."),
    ("atv320", "CFF", 405, "Option module changed or removed."),
    ("atv320", "CFI", 405, "Invalid configuration."),
    ("atv320", "CFI2", 405, "Invalid configuration."),
    ("atv320", "OHF", 413, None),
    ("atv320", "USF", 420, "Supply mains too low."),
    ("atv600", "ACF1", 645, None),
    ("atv600", "DRYF", 652, None),
    ("atv600", "OCF", 672, "Inertia or load too high."),
    ("atv600", "OHF", 672, "Ambient temperature too high."),
    ("atv600", "OLC", 672, "Mechanical root cause in the application."),
    ("atv600", "TNF", 686, None),
    ("atv600", "USF", 687, None),
    ("atv600", "VCF", 687, "Invalid power reference curve"),
    ("atv900", "BLF", 651, None),
    ("atv900", "ENF", 661, None),
    ("atv900", "OBF", 679, None),
    ("atv900", "OCF", 680, None),
    ("atv900", "OHF", 680, None),
    ("atv900", "PHF", 684, "One mains input or more phases are unavailable."),
    ("atv900", "SAFF", 684, "Internal hardware error."),
    ("atv900", "SPF", 689, None),
]


@pytest.mark.parametrize("manual_id,code,page,cause", GOLDEN)
def test_golden_fault_records(manual_id, code, page, cause):
    record = {f.code: f for f in _extract(manual_id).faults}[code]
    assert record.page == page
    assert record.causes and record.remedies
    if cause:
        assert any(cause in item for item in record.causes)
