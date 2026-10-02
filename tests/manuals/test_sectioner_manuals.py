import pytest

from faultsense.ingest.sectioner import build_section_chunks

pytestmark = pytest.mark.manuals


def test_atv12_before_you_begin_is_the_safety_chunk(manual_doc):
    spec, doc = manual_doc("atv12")
    result = build_section_chunks(doc, "atv12", safety_pages=set(spec.safety_pages))
    safety = [c for c in result.chunks if c.kind == "safety"]
    assert safety and all(c.page_start == 5 for c in safety)
    assert any("Disconnect all power" in c.text for c in safety)
    assert any(c.heading_path.endswith("Drive does not start, no error code displayed") for c in result.chunks)
    assert len(result.titles_not_found) <= 15
