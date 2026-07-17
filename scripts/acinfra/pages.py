"""Recovering PDF page numbers for each chapter from the LaTeX `.aux` file.

`main.tex` already carries JPTeX's auto-inserted markers::

    \\label{jptex@pageStart@ch02}

which LaTeX resolves into the `.aux` as `\\newlabel{...}{{n}{page}...}`. Reading
them back is what ties "PDF の 12 ページ" to a source file.
"""

from __future__ import annotations

import re
from pathlib import Path

from .latex import read_group

_PAGE_LABEL = re.compile(r"^\\newlabel\{jptex@pageStart@(?P<chapter>[^}]+)\}", re.MULTILINE)


def _page_from_entry(source: str, index: int) -> int | None:
    """Read the page number out of a `\\newlabel` value group.

    The value looks like `{{2}{7}{...}{...}{}}`: an outer group whose first two
    inner groups are the reference number and the page.
    """
    outer = read_group(source, index, "{")
    if outer is None:
        return None
    inner = read_group(outer.body, 0, "{")
    if inner is None:
        return None
    page_group = read_group(outer.body, inner.end, "{")
    if page_group is None:
        return None
    try:
        return int(page_group.body.strip())
    except ValueError:
        return None


def read_chapter_pages(aux_file: Path) -> dict[str, int]:
    """Map chapter stem (e.g. "ch02") to its first PDF page."""
    if not aux_file.exists():
        return {}
    source = aux_file.read_text(encoding="utf-8", errors="replace")

    pages: dict[str, int] = {}
    for match in _PAGE_LABEL.finditer(source):
        page = _page_from_entry(source, match.end())
        if page is not None:
            pages[match.group("chapter")] = page
    return pages


def resolve_page_range(
    stem: str, ordered_stems: list[str], pages: dict[str, int], total_pages: int
) -> tuple[int | None, int | None]:
    """Return (page_start, page_end) for one chapter.

    The first chapter has no JPTeX marker (nothing precedes it), so it starts at
    page 1. A chapter ends where the next one begins.
    """
    if not ordered_stems:
        return (None, None)

    position = ordered_stems.index(stem)
    start = pages.get(stem, 1 if position == 0 else None)
    if start is None:
        return (None, None)

    for following in ordered_stems[position + 1 :]:
        next_start = pages.get(following)
        if next_start is not None:
            return (start, max(start, next_start - 1))
    return (start, total_pages or None)
