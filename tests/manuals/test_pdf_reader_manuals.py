import pytest

pytestmark = pytest.mark.manuals


def test_atv600_page_numbers_and_running_headers(manual_doc):
    _, doc = manual_doc("atv600")
    assert doc.page_count == 692
    assert doc.page_mismatches() == []
    assert sum(page.printed_number is not None for page in doc.pages) >= 680
    texts = [line.text for line in doc.page(672).lines]
    assert "EAV64318.14" not in texts
    assert "Variable Speed Drives for Asynchronous and Synchronous" not in texts
    assert any(text.startswith("[Device Overheat]") for text in texts)


def test_internal_error_headings_survive_header_removal(manual_doc):
    _, doc = manual_doc("atv600")
    headings = [
        line for line in doc.iter_lines(659, 666)
        if line.text.startswith("[Internal Error") and line.spans[0].size >= 15
    ]
    assert len(headings) == 27
