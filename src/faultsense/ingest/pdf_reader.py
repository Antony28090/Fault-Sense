"""Read a PDF into lines with font information, minus running headers and footers."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pymupdf

pymupdf.TOOLS.mupdf_display_errors(False)

CODE_FONT_RE = re.compile(r"DigitFont|CourierNew", re.IGNORECASE)
TOP_BAND = 0.08
BOTTOM_BAND = 0.92
MIN_REPEATS = 3
_PAGE_NUMBER_RE = re.compile(r"\d{1,4}")


@dataclass(frozen=True)
class Span:
    text: str
    font: str
    size: float

    @property
    def bold(self) -> bool:
        return "Bold" in self.font

    @property
    def italic(self) -> bool:
        return "Italic" in self.font or "Oblique" in self.font

    @property
    def is_code_font(self) -> bool:
        return bool(CODE_FONT_RE.search(self.font))


@dataclass(frozen=True)
class Line:
    page: int
    index: int
    bbox: tuple[float, float, float, float]
    spans: tuple[Span, ...]

    @property
    def text(self) -> str:
        return "".join(span.text for span in self.spans).strip()

    @property
    def id(self) -> tuple[int, int]:
        return (self.page, self.index)


@dataclass
class Page:
    number: int
    width: float
    height: float
    lines: list[Line]
    printed_number: int | None = None


@dataclass
class PdfDocument:
    path: Path
    toc: list[tuple[int, str, int]]
    pages: list[Page]

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def page(self, number: int) -> Page:
        return self.pages[number - 1]

    def iter_lines(self, first: int = 1, last: int | None = None) -> Iterator[Line]:
        for number in range(first, (last or self.page_count) + 1):
            yield from self.page(number).lines

    def page_mismatches(self) -> list[tuple[int, int]]:
        return [
            (page.number, page.printed_number)
            for page in self.pages
            if page.printed_number is not None and page.printed_number != page.number
        ]


def _page_lines(page: pymupdf.Page, number: int) -> list[Line]:
    lines: list[Line] = []
    for block in page.get_text("dict")["blocks"]:
        for raw in block.get("lines", []):
            spans = tuple(
                Span(s["text"], s["font"], round(s["size"], 1))
                for s in raw["spans"]
                if s["text"].strip()
            )
            if spans:
                lines.append(Line(number, len(lines), tuple(raw["bbox"]), spans))
    return lines


def _in_band(line: Line, height: float) -> bool:
    return line.bbox[3] <= TOP_BAND * height or line.bbox[1] >= BOTTOM_BAND * height


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def read_pdf(path: Path) -> PdfDocument:
    """Lines in reading order with fonts.

    Drops text that repeats in the header/footer band on 3+ pages and bare page numbers
    (recorded as `printed_number`). Repeats are matched on exact text: normalising digits
    would delete headings such as `[Internal Error 1] INF1`.
    """
    with pymupdf.open(path) as pdf:
        raw = [(p.rect.width, p.rect.height, _page_lines(p, i + 1)) for i, p in enumerate(pdf)]
        toc = [(level, title.strip(), page) for level, title, page in pdf.get_toc()]
    repeats: Counter[str] = Counter()
    for _, height, lines in raw:
        repeats.update({_norm(line.text) for line in lines if _in_band(line, height)})
    running = {text for text, count in repeats.items() if count >= MIN_REPEATS}
    pages = []
    for number, (width, height, lines) in enumerate(raw, start=1):
        kept, printed = [], None
        for line in lines:
            if _in_band(line, height):
                if _PAGE_NUMBER_RE.fullmatch(line.text):
                    printed = int(line.text)
                    continue
                if _norm(line.text) in running:
                    continue
            kept.append(line)
        pages.append(Page(number, width, height, kept, printed))
    return PdfDocument(Path(path), toc, pages)
