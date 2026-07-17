#!/usr/bin/env python3
"""Insert REVIEW-ID headers into a course's chapter files.

    python3 scripts/add_review_headers.py --repo-root ../logic-notes --dry-run

Used when onboarding a course. Writing the headers by hand across a dozen
chapters invites typos in exactly the identifier everything else keys off.

REVIEW-TITLE comes from the chapter's `\\section{...}`. REVIEW-KEYWORDS come
from the titles of the definition/theorem-like boxes in the chapter, which is
what someone would actually name when asking for "あの定義のところ".

Chapter slugs cannot be derived from Japanese titles, so the id defaults to
`<course_id>.<stem>` (e.g. `dsa.ch02`). Supply `review-slugs.yml` in the repo
root to get `dsa.ch02.list` instead:

    ch01: algorithm-complexity
    ch02: list
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acinfra.config import load_course_config
from acinfra.environments import THEOREM_BOXES
from acinfra.latex import read_arguments, read_group

_MAX_KEYWORDS = 12


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--dry-run", action="store_true", help="書き換えず、生成されるヘッダを表示する"
    )
    return parser.parse_args()


def _section_title(source: str) -> str:
    marker = r"\section"
    found = source.find(marker)
    if found == -1:
        return ""
    group = read_group(source, found + len(marker), "{")
    return group.body.strip() if group else ""


def _box_titles(source: str) -> list[str]:
    """Collect the titles of theorem-like boxes, preserving document order."""
    found: list[tuple[int, str]] = []
    for name in THEOREM_BOXES:
        opener = rf"\begin{{{name}}}"
        cursor = 0
        while True:
            position = source.find(opener, cursor)
            if position == -1:
                break
            arguments, after = read_arguments(source, position + len(opener), 2)
            if arguments and arguments[0].strip():
                found.append((position, arguments[0].strip()))
            cursor = max(after, position + len(opener))

    seen: set[str] = set()
    titles: list[str] = []
    for _, title in sorted(found):
        if title not in seen:
            seen.add(title)
            titles.append(title)
    return titles[:_MAX_KEYWORDS]


def _load_slugs(repo_root: Path) -> dict[str, str]:
    path = repo_root / "review-slugs.yml"
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(key): str(value) for key, value in raw.items()}


def build_header(course_id: str, stem: str, slug: str | None, title: str, keywords: list[str]) -> str:
    review_id = f"{course_id}.{stem}.{slug}" if slug else f"{course_id}.{stem}"
    lines = [f"% REVIEW-ID: {review_id}", f"% REVIEW-TITLE: {title}"]
    if keywords:
        lines.append("% REVIEW-KEYWORDS:")
        lines.extend(f"%   {keyword}" for keyword in keywords)
    return "\n".join(lines) + "\n"


def main() -> int:
    arguments = _parse_arguments()
    repo_root = arguments.repo_root.resolve()

    try:
        config = load_course_config(repo_root / "academic.yml")
    except (FileNotFoundError, ValueError) as error:
        print(f"設定エラー: {error}", file=sys.stderr)
        return 1

    slugs = _load_slugs(repo_root)
    changed = 0

    for tex_file in sorted(config.chapters_dir.glob("*.tex")):
        source = tex_file.read_text(encoding="utf-8")
        if "% REVIEW-ID:" in source:
            print(f"skip  {tex_file.name} (既にヘッダあり)")
            continue

        header = build_header(
            course_id=config.course_id,
            stem=tex_file.stem,
            slug=slugs.get(tex_file.stem),
            title=_section_title(source),
            keywords=_box_titles(source),
        )

        if arguments.dry_run:
            print(f"--- {tex_file.name} ---\n{header}")
            continue

        tex_file.write_text(header + source, encoding="utf-8")
        print(f"write {tex_file.name}")
        changed += 1

    if not arguments.dry_run:
        print(f"完了: {changed} ファイルにヘッダを追加しました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
