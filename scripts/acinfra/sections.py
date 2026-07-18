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


def _front_matter(section_review_id: str, title: str, chapter: ReviewHeader, repository: str) -> str:
    keywords = ", ".join(chapter.keywords)
    lines = [
        "---",
        f"review_id: {section_review_id}",
        f'title: "{title}"',
        f'chapter: "{chapter.title}"',
        f"chapter_review_id: {chapter.review_id}",
        f"source_file: {chapter.source_file}",
        f"keywords: [{keywords}]",
        f"repository: {repository}",
    ]
    if repository != "unknown":
        lines.append(f"issue_new_url: https://github.com/{repository}/issues/new?labels=review,needs-decision")
    lines.append("---\n\n")
    return "\n".join(lines)


def _iter_blocks(markdown: str) -> Iterator[tuple[str, str]]:
    """Yield (title, body) for each `##` block, ignoring any chapter preamble."""
    matches = list(_SECTION_HEADING.finditer(markdown))
    for position, match in enumerate(matches):
        start = match.end()
        end = matches[position + 1].start() if position + 1 < len(matches) else len(markdown)
        yield match.group("title"), markdown[start:end].strip()


def split_chapter(markdown: str, chapter: ReviewHeader, repository: str = "unknown") -> list[Section]:
    """Split one chapter's Markdown into sections.

    A chapter with no `##` headings yields a single section holding the whole
    chapter, so no content can fall out of the knowledge base. `repository` is
    stamped into each section's front matter so a reader with only that one
    file (e.g. GPT's Drive connector surfacing a single search hit) still has
    a direct `issues/new` link back to the right repo, not just the manifest.
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
                body=_front_matter(section_id, chapter.title, chapter, repository)
                + f"# {chapter.title}\n\n{body}\n",
                review_id=section_id,
            )
        ]

    sections: list[Section] = []
    for index, (title, body) in enumerate(blocks, start=1):
        section_id = f"{chapter.review_id}.s{index:02d}"
        file_name = f"{stem}-{index:02d}.md"
        content = _front_matter(section_id, title, chapter, repository) + f"# {title}\n\n{body}\n"
        sections.append(
            Section(file_name=file_name, title=title, body=content, review_id=section_id)
        )
    return sections
