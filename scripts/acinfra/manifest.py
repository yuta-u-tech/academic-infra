"""Building `review-manifest.json`, the index that ties PDF ⇄ Markdown ⇄ TeX."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import CourseConfig
from .review_id import ReviewHeader
from .sections import Section

MANIFEST_VERSION = 1


def current_commit(repo_root: Path) -> str:
    """Return the checked-out commit, or "unknown" when it cannot be resolved.

    In GitHub Actions the container often refuses `git rev-parse` over the
    mounted workspace ("dubious ownership"), so GITHUB_SHA is the reliable
    source there. It is preferred precisely because the git call is the one
    that fails in CI, which is where a correct commit matters most: the Issue
    template's Base Commit keys off it.
    """
    github_sha = os.environ.get("GITHUB_SHA", "").strip()
    if github_sha:
        return github_sha
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"
    return completed.stdout.strip()


def _chapter_entry(
    chapter: ReviewHeader,
    sections: list[Section],
    page_start: int | None,
    page_end: int | None,
    included_in_pdf: bool,
) -> dict[str, Any]:
    return {
        "review_id": chapter.review_id,
        "title": chapter.title,
        "keywords": list(chapter.keywords),
        "source_file": str(chapter.source_file),
        "included_in_pdf": included_in_pdf,
        "page_start": page_start,
        "page_end": page_end,
        "sections": [
            {
                "review_id": section.review_id,
                "title": section.title,
                "markdown_file": f"sections/{section.file_name}",
            }
            for section in sections
        ],
    }


def build_manifest(
    config: CourseConfig,
    repository: str,
    chapters: list[tuple[ReviewHeader, list[Section], int | None, int | None, bool]],
    total_pages: int,
) -> dict[str, Any]:
    """Assemble the manifest document."""
    issue_new_url = (
        f"https://github.com/{repository}/issues/new?labels=review,needs-decision"
        if repository != "unknown"
        else None
    )
    return {
        "manifest_version": MANIFEST_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repository": repository,
        "issue_new_url": issue_new_url,
        "commit": current_commit(config.main_tex.parent.parent),
        "course_id": config.course_id,
        "course_name": config.course_name,
        "pdf_file": "latest.pdf",
        "markdown_file": "latest.md",
        "total_pages": total_pages,
        "chapters": [
            _chapter_entry(chapter, sections, page_start, page_end, included)
            for chapter, sections, page_start, page_end, included in chapters
        ],
    }


def write_manifest(manifest: dict[str, Any], output_dir: Path) -> Path:
    """Write the manifest as pretty-printed UTF-8 JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / "review-manifest.json"
    destination.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return destination
