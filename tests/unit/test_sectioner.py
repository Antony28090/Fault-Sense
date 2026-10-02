from helpers import make_doc
from faultsense.ingest.sectioner import build_section_chunks

TOC = [(1, "Intro", 1), (1, "Wiring", 2), (2, "Power terminals", 2)]
PAGES = {
    1: ["Intro", "Intro text a"],
    2: ["Wiring", "Wiring text", "Power terminals", "Terminal text"],
    3: ["more terminal text"],
}


def test_sections_follow_toc_headings_with_paths_and_page_ranges():
    result = build_section_chunks(make_doc(PAGES, TOC), "m1")
    got = [(c.heading_path, c.page_start, c.page_end, c.text, c.kind) for c in result.chunks]
    assert got == [
        ("Intro", 1, 1, "Intro\nIntro text a", "section"),
        ("Wiring", 2, 2, "Wiring\nWiring text", "section"),
        ("Wiring > Power terminals", 2, 3, "Power terminals\nTerminal text\nmore terminal text", "section"),
    ]
    assert [c.id for c in result.chunks] == ["m1:s00000", "m1:s00001", "m1:s00002"]
    assert result.titles_not_found == []


def test_excluded_lines_are_dropped():
    result = build_section_chunks(make_doc(PAGES, TOC), "m1", exclude={(2, 1)})
    assert result.chunks[1].text == "Wiring"


def test_long_section_splits_at_line_boundaries_and_keeps_heading():
    lines = ["Big"] + [f"line {i:02d} " + "x" * 90 for i in range(30)]
    result = build_section_chunks(make_doc({1: lines}, [(1, "Big", 1)]), "m1", max_chars=1000)
    assert len(result.chunks) > 1
    assert all(c.heading_path == "Big" for c in result.chunks)
    assert all(len(c.text) <= 1000 for c in result.chunks)
    assert "\n".join(c.text for c in result.chunks).count("line ") == 30


def test_safety_pages_form_one_unsplit_safety_chunk():
    pages = {
        1: ["Safety", "DANGER " + "y" * 200, "Disconnect all power " + "z" * 200],
        2: ["Next", "text"],
    }
    toc = [(1, "Safety", 1), (1, "Next", 2)]
    result = build_section_chunks(make_doc(pages, toc), "m1", safety_pages={1}, max_chars=100)
    assert [(c.kind, c.heading_path) for c in result.chunks] == [("safety", "Safety"), ("section", "Next")]


def test_contents_sections_and_dotted_leaders_are_dropped():
    pages = {
        1: ["Table of Contents", "Wiring ........................ 2"],
        2: ["Wiring", "See Setup ........ 12", "Real text"],
    }
    toc = [(1, "Table of Contents", 1), (1, "Wiring", 2)]
    result = build_section_chunks(make_doc(pages, toc), "m1")
    assert [c.text for c in result.chunks] == ["Wiring\nReal text"]


def test_missing_heading_starts_section_at_page_top_and_is_reported():
    pages = {1: ["Intro", "a"], 2: ["b", "c"]}
    result = build_section_chunks(make_doc(pages, [(1, "Intro", 1), (1, "Ghost title", 2)]), "m1")
    assert [(c.heading_path, c.text) for c in result.chunks] == [("Intro", "Intro\na"), ("Ghost title", "b\nc")]
    assert result.titles_not_found == ["p2: Ghost title"]
