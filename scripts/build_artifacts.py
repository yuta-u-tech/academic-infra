#!/usr/bin/env python3
"""Build every publishable artefact for one course repository.

    python3 scripts/build_artifacts.py --repo-root ../logic-notes

Produces, under the repo's `output_dir` (default `dist/`):

    latest.pdf              the compiled document
    latest.md               the whole document as Markdown
    sections/chNN-MM.md     retrieval-sized pieces with front matter
    review-manifest.json    PDF page ⇄ Markdown ⇄ TeX index
    build.log               the LaTeX log, kept for debugging

This is the single entry point used by both local runs and CI, so that a green
CI run means the same thing as a green local run.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acinfra.build import build_pdf, chapters_in_main, stage_pdf
from acinfra.config import CourseConfig, load_course_config
from acinfra.manifest import build_manifest, write_manifest
from acinfra.markdown import convert_to_markdown
from acinfra.pages import read_chapter_pages, resolve_page_range
from acinfra.review_id import ReviewHeader, collect_review_headers
from acinfra.sections import Section, split_chapter


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="科目リポジトリのルート (academic.yml のある場所)",
    )
    parser.add_argument(
        "--repository",
        default="",
        help="owner/name 形式のリポジトリ名。CI では GITHUB_REPOSITORY を渡す",
    )
    parser.add_argument(
        "--skip-pdf",
        action="store_true",
        help="LaTeX ビルドを飛ばし、Markdown と manifest だけ生成する",
    )
    return parser.parse_args()


def _write_sections(sections: list[Section], output_dir: Path) -> None:
    sections_dir = output_dir / "sections"
    if sections_dir.exists():
        # Stale files would linger after a heading is removed and keep being
        # served to the knowledge base as if they were current.
        shutil.rmtree(sections_dir)
    sections_dir.mkdir(parents=True)
    for section in sections:
        (sections_dir / section.file_name).write_text(section.body, encoding="utf-8")


def _write_latest_markdown(config: CourseConfig, chapter_markdown: list[str]) -> Path:
    destination = config.output_dir / "latest.md"
    header = f"# {config.course_name}\n\n"
    destination.write_text(header + "\n\n---\n\n".join(chapter_markdown) + "\n", encoding="utf-8")
    return destination


def main() -> int:
    arguments = _parse_arguments()
    repo_root = arguments.repo_root.resolve()

    try:
        config = load_course_config(repo_root / "academic.yml")
    except (FileNotFoundError, ValueError) as error:
        print(f"設定エラー: {error}", file=sys.stderr)
        return 1

    headers = collect_review_headers(config.chapters_dir, repo_root)
    if not headers:
        print(
            f"エラー: {config.chapters_dir} に REVIEW-ID ヘッダを持つ .tex がありません。",
            file=sys.stderr,
        )
        return 1

    included = chapters_in_main(config.main_tex)
    pages: dict[str, int] = {}
    total_pages = 0

    if not arguments.skip_pdf:
        try:
            result = build_pdf(config)
        except RuntimeError as error:
            print(f"ビルドエラー: {error}", file=sys.stderr)
            return 1
        stage_pdf(result, config)
        pages = read_chapter_pages(result.aux)
        total_pages = result.total_pages
        shutil.copy2(result.log, config.output_dir / "build.log")

    config.output_dir.mkdir(parents=True, exist_ok=True)
    all_sections: list[Section] = []
    chapter_markdown: list[str] = []
    manifest_rows: list[tuple[ReviewHeader, list[Section], int | None, int | None, bool]] = []

    for header in headers:
        stem = header.source_file.stem
        try:
            markdown = convert_to_markdown(
                (repo_root / header.source_file).read_text(encoding="utf-8")
            )
        except RuntimeError as error:
            print(f"Markdown 変換エラー ({header.source_file}): {error}", file=sys.stderr)
            return 1

        sections = split_chapter(markdown, header)
        all_sections.extend(sections)
        chapter_markdown.append(markdown)

        is_included = stem in included
        page_start, page_end = (
            resolve_page_range(stem, included, pages, total_pages) if is_included else (None, None)
        )
        manifest_rows.append((header, sections, page_start, page_end, is_included))

        if not is_included:
            print(f"警告: {header.source_file} は main.tex に \\subfile されておらず PDF に載りません。")

    _write_sections(all_sections, config.output_dir)
    _write_latest_markdown(config, chapter_markdown)
    manifest = build_manifest(
        config,
        repository=arguments.repository or "unknown",
        chapters=manifest_rows,
        total_pages=total_pages,
    )
    write_manifest(manifest, config.output_dir)

    print(
        f"完了: {len(headers)} 章 / {len(all_sections)} セクション / {total_pages} ページ"
        f" → {config.output_dir}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
