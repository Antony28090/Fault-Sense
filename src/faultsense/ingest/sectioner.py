"""Heading-based chunks: sections follow the PDF bookmark outline, never fixed windows."""
from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field

from faultsense.ingest.pdf_reader import Line, PdfDocument

MAX_CHARS = 2800
_LEADER_RE = re.compile(r"\.{5,}\s*\d+\s*$")
_SKIP_TITLE_RE = re.compile(r"^(table of contents|contents)$", re.IGNORECASE)


@dataclass(frozen=True)
class Chunk:
    id: str
    manual_id: str
    kind: str  # section | fault | safety
    heading_path: str
    page_start: int
    page_end: int
    text: str


@dataclass
class SectionResult:
    chunks: list[Chunk]
    titles_not_found: list[str] = field(default_factory=list)


def _norm_title(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _matches(line_text: str, title: str) -> bool:
    line, wanted = _norm_title(line_text), _norm_title(title)
    if not line or not wanted:
        return False
    return (
        line == wanted
        or (len(wanted) >= 8 and line.startswith(wanted[:40]))
        or (len(line) >= 8 and wanted.startswith(line))
    )


def _section_starts(doc: PdfDocument, lines: list[Line]) -> tuple[list[tuple[int, str, str]], list[str]]:
    """(line index, heading path, title) per outline entry; the heading line is looked up on its
    page, and when it cannot be found the section starts at the top of that page."""
    pages = [line.page for line in lines]
    starts: list[tuple[int, str, str]] = []
    missing: list[str] = []
    stack: list[str] = []
    previous = 0
    for level, title, page in doc.toc:
        if not 1 <= page <= doc.page_count:
            continue
        stack = stack[: max(level - 1, 0)] + [title]
        lo = max(previous, bisect.bisect_left(pages, page))
        hi = bisect.bisect_left(pages, page + 1)
        index = next((i for i in range(lo, hi) if _matches(lines[i].text, title)), None)
        if index is None:
            missing.append(f"p{page}: {title}")
            index = lo
        starts.append((index, " > ".join(stack), title))
        previous = index
    if not starts:
        starts.append((0, doc.path.stem, ""))
    return starts, missing


def _runs(lines: list[Line], safety_pages) -> list[tuple[str, list[Line]]]:
    runs: list[tuple[str, list[Line]]] = []
    for line in lines:
        kind = "safety" if line.page in safety_pages else "section"
        if runs and runs[-1][0] == kind:
            runs[-1][1].append(line)
        else:
            runs.append((kind, [line]))
    return runs


def _split(lines: list[Line], max_chars: int) -> list[list[Line]]:
    pieces: list[list[Line]] = []
    current: list[Line] = []
    size = 0
    for line in lines:
        length = len(line.text) + 1
        if current and size + length > max_chars:
            pieces.append(current)
            current, size = [], 0
        current.append(line)
        size += length
    if current:
        pieces.append(current)
    return pieces


def build_section_chunks(
    doc: PdfDocument,
    manual_id: str,
    exclude=frozenset(),
    safety_pages=frozenset(),
    max_chars: int = MAX_CHARS,
) -> SectionResult:
    """One chunk per outline section (split at line boundaries when longer than `max_chars`).

    Lines in `exclude` (fault content, parsed separately) and dotted-leader lines are dropped.
    Lines on `safety_pages` form one unsplit `safety` chunk per section.
    """
    lines = list(doc.iter_lines())
    starts, missing = _section_starts(doc, lines)
    chunks: list[Chunk] = []
    for n, (start, path, title) in enumerate(starts):
        if _SKIP_TITLE_RE.match(title.strip()):
            continue
        end = starts[n + 1][0] if n + 1 < len(starts) else len(lines)
        body = [
            line for line in lines[start:end]
            if line.id not in exclude and not _LEADER_RE.search(line.text)
        ]
        for kind, run in _runs(body, safety_pages):
            for piece in [run] if kind == "safety" else _split(run, max_chars):
                text = "\n".join(line.text for line in piece).strip()
                if text:
                    chunks.append(Chunk(
                        f"{manual_id}:s{len(chunks):05d}", manual_id, kind, path,
                        piece[0].page, piece[-1].page, text,
                    ))
    return SectionResult(chunks, missing)
