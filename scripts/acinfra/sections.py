"""Splitting chapter Markdown into retrieval-sized section files.

A whole chapter is too coarse for an AI to quote precisely and too large to
pull into context repeatedly, so each `##` heading (a `\\subsection` in the
source) becomes its own file carrying front matter that names it.

Filenames are index-based (`ch02-03.md`) rather than derived from the Japanese
heading: transliterating 日本語 headings into slugs is lossy and unstable, and
a heading edit would silently rename the file and break every existing link.
The human-readable title travels in the front matter instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator

from .review_id import ReviewHeader

_SECTION_HEADING = re.compile(r"^##\s+(?P<title>.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Section:
    """One `##` block of a chapter, ready to be written to disk."""

    file_name: str
    title: str
    body: str
    review_id: str


def _front_matter(section_review_id: str, title: str, chapter: ReviewHeader) -> str:
    keywords = ", ".join(chapter.keywords)
    return (
        "---\n"
        f"review_id: {section_review_id}\n"
        f'title: "{title}"\n'
        f'chapter: "{chapter.title}"\n'
        f"chapter_review_id: {chapter.review_id}\n"
        f"source_file: {chapter.source_file}\n"
        f"keywords: [{keywords}]\n"
        "---\n\n"
    )


def _iter_blocks(markdown: str) -> Iterator[tuple[str, str]]:
    """Yield (title, body) for each `##` block, ignoring any chapter preamble."""
    matches = list(_SECTION_HEADING.finditer(markdown))
    for position, match in enumerate(matches):
        start = match.end()
        end = matches[position + 1].start() if position + 1 < len(matches) else len(markdown)
        yield match.group("title"), markdown[start:end].strip()


def split_chapter(markdown: str, chapter: ReviewHeader) -> list[Section]:
    """Split one chapter's Markdown into sections.

    A chapter with no `##` headings yields a single section holding the whole
    chapter, so no content can fall out of the knowledge base.
    """
    stem = chapter.source_file.stem  # e.g. "ch02"
    blocks = list(_iter_blocks(markdown))

    if not blocks:
        body = markdown.strip()
        if not body:
            return []
        section_id = f"{chapter.review_id}.full"
        return [
            Section(
                file_name=f"{stem}.md",
                title=chapter.title,
                body=_front_matter(section_id, chapter.title, chapter)
                + f"# {chapter.title}\n\n{body}\n",
                review_id=section_id,
            )
        ]

    sections: list[Section] = []
    for index, (title, body) in enumerate(blocks, start=1):
        section_id = f"{chapter.review_id}.s{index:02d}"
        file_name = f"{stem}-{index:02d}.md"
        content = _front_matter(section_id, title, chapter) + f"# {title}\n\n{body}\n"
        sections.append(
            Section(file_name=file_name, title=title, body=content, review_id=section_id)
        )
    return sections
