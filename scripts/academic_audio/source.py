"""Resolve Academic-Infra materials into audio sources."""

from __future__ import annotations

import json
from pathlib import Path

from .models import AudioSource


class AudioSourceError(Exception):
    pass


def _strip_front_matter(markdown: str) -> str:
    if not markdown.startswith("---"):
        return markdown.strip()
    end = markdown.find("\n---", 3)
    if end == -1:
        return markdown.strip()
    return markdown[end + 4 :].strip()


def resolve_source(
    *,
    review_id: str | None = None,
    source_path: Path | None = None,
    repo_root: Path | None = None,
    course: str | None = None,
) -> AudioSource:
    if source_path is not None:
        body = source_path.read_text(encoding="utf-8")
        return AudioSource(
            source_id=str(source_path),
            title=source_path.stem,
            course_id=course,
            review_id=review_id,
            source_file=str(source_path),
            section_file=str(source_path),
            source_commit="local",
            body=_strip_front_matter(body),
        )
    if review_id is None:
        raise AudioSourceError("--review-id または --source のどちらかが必要です。")
    return _resolve_manifest_source(review_id, repo_root, course)


def _resolve_manifest_source(review_id: str, repo_root: Path | None, course: str | None) -> AudioSource:
    root = repo_root or Path.cwd()
    manifest_path = root / "dist" / "review-manifest.json"
    if not manifest_path.exists():
        raise AudioSourceError(f"{manifest_path} がありません。--repo-root で科目リポジトリを指定してください。")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dist = root / "dist"
    for chapter in manifest.get("chapters", []):
        if chapter.get("review_id") == review_id:
            md_path = dist / str(manifest.get("markdown_file", "latest.md"))
            body = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
            return AudioSource(
                source_id=review_id,
                title=chapter.get("title", review_id),
                course_id=manifest.get("course_id", course),
                review_id=review_id,
                source_file=chapter.get("source_file"),
                section_file=None,
                source_commit=manifest.get("commit", "unknown"),
                body=_strip_front_matter(body),
            )
        for section in chapter.get("sections", []):
            if section.get("review_id") != review_id:
                continue
            rel = section["markdown_file"]
            path = dist / rel
            if not path.exists():
                raise AudioSourceError(f"{path} がありません。manifest と sections を再生成してください。")
            return AudioSource(
                source_id=review_id,
                title=section.get("title", review_id),
                course_id=manifest.get("course_id", course),
                review_id=review_id,
                source_file=chapter.get("source_file"),
                section_file=rel,
                source_commit=manifest.get("commit", "unknown"),
                body=_strip_front_matter(path.read_text(encoding="utf-8")),
            )
    raise AudioSourceError(f"REVIEW-ID '{review_id}' が {manifest_path} にありません。")
