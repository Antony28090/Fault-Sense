"""The real-world scenarios point at fault entries that really exist on the stated manual pages."""
import pytest

from helpers import DATA_DIR
from faultsense.codes import code_key
from faultsense.eval.scenarios import load_scenarios
from faultsense.ingest.extract import extract_manual
from faultsense.manifest import load_manuals

pytestmark = pytest.mark.manuals


@pytest.fixture(scope="module")
def fault_pages():
    pages = {}
    for spec in load_manuals(DATA_DIR / "manuals.yaml"):
        path = DATA_DIR / "manuals" / spec.file
        if not path.exists():
            pytest.skip("run `faultsense fetch-manuals` first")
        for fault in extract_manual(spec, DATA_DIR / "manuals").faults:
            pages.setdefault((spec.id, code_key(fault.code)), set()).update(range(fault.page, fault.page_end + 1))
    return pages


def test_expected_fault_codes_are_on_the_expected_pages(fault_pages):
    for s in load_scenarios(DATA_DIR / "eval" / "scenarios_web.yaml"):
        for code in s.expected_fault_codes:
            found = [(src.manual, p) for src in s.expected_sources for p in src.pages
                     if p in fault_pages.get((src.manual, code_key(code)), set())]
            assert found, f"{s.id}: {code} is not on any expected page {s.expected_sources}"
