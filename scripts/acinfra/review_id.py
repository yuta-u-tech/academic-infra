"""Parsing the REVIEW-ID header block at the top of each chapter file.

The header is what lets "自然演繹のところを添削して" resolve to a file without
the AI reading every chapter::

    % REVIEW-ID: dsa.ch02.list
    % REVIEW-TITLE: リスト
    % REVIEW-KEYWORDS:
    %   線形リスト
    %   環状リスト

Parsing stops at the first non-comment line, so the header must lead the file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_FIELD = re.compile(r"^%\s*REVIEW-(?P<key>[A-Z-]+)\s*:\s*(?P<value>.*)$")
_CONTINUATION = re.compile(r"^%\s+(?P<value>\S.*)$")


@dataclass(frozen=True)
class ReviewHeader:
    """Metadata declared at the top of a chapter file."""

    review_id: str
    title: str
    keywords: tuple[str, ...]
    source_file: Path


def parse_review_header(path: Path, repo_root: Path) -> ReviewHeader | None:
    """Return the header declared in `path`, or None when there is none."""
    fields: dict[str, str] = {}
    keywords: list[str] = []
    current_key: str | None = None

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("%"):
            break

        field = _FIELD.match(stripped)
        if field:
            current_key = field.group("key")
            value = field.group("value").strip()
            if value:
                fields[current_key] = value
            continue

        # An indented comment line continues the previous field. Only KEYWORDS
        # is list-valued today; anything else keeps its first line.
        continuation = _CONTINUATION.match(stripped)
        if continuation and current_key == "KEYWORDS":
            keywords.append(continuation.group("value").strip())

    if "ID" not in fields:
        return None

    inline_keywords = fields.get("KEYWORDS", "")
    if inline_keywords:
        keywords = [part.strip() for part in inline_keywords.split(",") if part.strip()]

    return ReviewHeader(
        review_id=fields["ID"],
        title=fields.get("TITLE", ""),
        keywords=tuple(keywords),
        source_file=path.relative_to(repo_root),
    )


def collect_review_headers(chapters_dir: Path, repo_root: Path) -> list[ReviewHeader]:
    """Parse headers from every `.tex` file in `chapters_dir`, sorted by name."""
    headers: list[ReviewHeader] = []
    for tex_file in sorted(chapters_dir.glob("*.tex")):
        header = parse_review_header(tex_file, repo_root)
        if header is not None:
            headers.append(header)
    return headers
