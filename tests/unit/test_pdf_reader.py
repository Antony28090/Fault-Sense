import pymupdf

from faultsense.ingest.pdf_reader import read_pdf


def _make_pdf(path):
    doc = pymupdf.open()
    for n in range(1, 5):
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 30), "Acme Drive Manual", fontsize=9)
        page.insert_text((50, 200), f"Section {n} heading", fontsize=14)
        page.insert_text((50, 230), f"Body text on page {n}", fontsize=10)
        if n == 2:
            page.insert_text((50, 60), "Unique top note", fontsize=9)
        page.insert_text((50, 810), "DOC123 01/2026", fontsize=8)
        page.insert_text((540, 835), str(n), fontsize=8)
    doc.set_toc([[1, "Section 1 heading", 1], [1, "Section 3 heading", 3]])
    doc.save(path)
    doc.close()


def test_running_header_footer_and_page_numbers_are_removed(tmp_path):
    path = tmp_path / "m.pdf"
    _make_pdf(path)
    doc = read_pdf(path)
    texts = [line.text for page in doc.pages for line in page.lines]
    assert "Acme Drive Manual" not in texts
    assert "DOC123 01/2026" not in texts
    assert [page.printed_number for page in doc.pages] == [1, 2, 3, 4]
    assert doc.page_mismatches() == []


def test_unique_band_text_and_body_are_kept(tmp_path):
    path = tmp_path / "m.pdf"
    _make_pdf(path)
    doc = read_pdf(path)
    assert "Unique top note" in [line.text for line in doc.page(2).lines]
    assert [line.text for line in doc.page(3).lines] == ["Section 3 heading", "Body text on page 3"]
    assert len(list(doc.iter_lines(2, 3))) == 5


def test_toc_fonts_and_line_ids(tmp_path):
    path = tmp_path / "m.pdf"
    _make_pdf(path)
    doc = read_pdf(path)
    assert doc.toc == [(1, "Section 1 heading", 1), (1, "Section 3 heading", 3)]
    heading = doc.page(1).lines[0]
    assert heading.spans[0].size == 14.0
    assert heading.id == (1, heading.index)
    assert doc.page_count == 4
