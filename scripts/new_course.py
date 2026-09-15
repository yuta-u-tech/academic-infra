#!/usr/bin/env python3
"""Scaffold a new academic-infra course repository.

Onboarding a course is currently 6 manual steps (see README「新しい科目を追加する」),
and in practice most of the actual file content (main.tex / preamble.tex /
protocol.tex / .gitignore) has been copy-pasted from whichever course repo was
open at the time rather than from a canonical source. This script does all of
it in one shot, from the templates in ``templates/``:

    python3 scripts/new_course.py \\
      --id mathematical-optimization \\
      --name 数理最適化 \\
      --repo yuta-u-tech/Mathematical_Optimization \\
      --local-path ~/Mathematical_Optimization \\
      --alias 最適化 --alias optimization

Prerequisite: ``--local-path`` is an already-`git clone`d (possibly empty)
checkout of ``--repo``. This script does not create the GitHub repository or
run any git commands — it only writes files. Review the diff, then commit and
push both the course repo and this repo's ``courses.yml`` yourself.

What gets written:
    <local-path>/academic.yml                        (from templates/academic.yml)
    <local-path>/AGENTS.md                            (from templates/AGENTS.md, verbatim)
    <local-path>/.github/workflows/document.yml       (from templates/document.yml, verbatim)
    <local-path>/.gitignore                           (from templates/gitignore, verbatim)
    <local-path>/src/main.tex                         (from templates/main.tex, {{COURSE_NAME}} filled in)
    <local-path>/src/includes/preamble.tex             (from templates/preamble.tex, verbatim)
    <local-path>/src/includes/protocol.tex             (from templates/protocol.tex, verbatim)
    <local-path>/src/chapters/.gitkeep                (empty dir placeholder — git doesn't track empty dirs)
    courses.yml                                        (new entry appended)

Not done here (out of scope — happens once chapters actually exist):
    scripts/add_review_headers.py --repo-root <local-path>
"""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

ACADEMIC_INFRA_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ACADEMIC_INFRA_ROOT / "templates"
COURSES_YML = ACADEMIC_INFRA_ROOT / "courses.yml"

_DEFAULT_EXCLUDE = ("Lecture_Materials", "Code")

# Files copied byte-for-byte into the new repo (destination relative to --local-path).
_VERBATIM_FILES = {
    "AGENTS.md": "AGENTS.md",
    "document.yml": ".github/workflows/document.yml",
    "gitignore": ".gitignore",
    "preamble.tex": "src/includes/preamble.tex",
    "protocol.tex": "src/includes/protocol.tex",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--id", required=True, help="course_id (英小文字・数字・ハイフンのみ)")
    parser.add_argument("--name", required=True, help="course_name (人間向け科目名)")
    parser.add_argument("--repo", required=True, help="owner/repo (courses.yml の repository)")
    parser.add_argument(
        "--local-path", type=Path, required=True,
        help="git clone 済みの科目リポジトリのローカルパス",
    )
    parser.add_argument("--visibility", choices=("public", "private"), default="private")
    parser.add_argument("--drive-folder", default=None, help="省略時は --name と同じ")
    parser.add_argument(
        "--alias", action="append", default=[],
        help="courses.yml の aliases に追加する呼び方 (複数指定可。--name 自体は自動で入る)",
    )
    parser.add_argument("--status", default="pilot")
    parser.add_argument(
        "--exclude", action="append", default=None,
        help="exclude_from_publish (省略時は Lecture_Materials, Code)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="local-path に既にあるファイルを上書きする (既定は既存ファイルがあれば中断)",
    )
    parser.add_argument("--dry-run", action="store_true", help="書き込まず、行う変更を表示する")
    return parser.parse_args()


def _validate_course_id(course_id: str) -> None:
    if not course_id or not all(c.islower() or c == "-" or c.isdigit() for c in course_id):
        raise SystemExit(f"--id は英小文字・数字・ハイフンのみ: {course_id!r}")


def _load_courses() -> dict:
    return yaml.safe_load(COURSES_YML.read_text(encoding="utf-8")) or {}


def _check_not_registered(course_id: str) -> None:
    if course_id in (_load_courses().get("courses") or {}):
        raise SystemExit(f"courses.yml に {course_id!r} は既に登録されています。")


def _render_academic_yml(course_id: str, course_name: str, drive_folder: str,
                          exclude: tuple[str, ...]) -> str:
    lines = (TEMPLATES / "academic.yml").read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("course_id:"):
            out.append(f"course_id: {course_id}")
        elif line.startswith("course_name:"):
            out.append(f"course_name: {course_name}")
        elif line.startswith("drive_folder_name:"):
            out.append(f"drive_folder_name: {drive_folder}")
        elif line.startswith("exclude_from_publish:"):
            out.append(line)
            i += 1
            while i < len(lines) and lines[i].startswith("  - "):
                i += 1
            out.extend(f"  - {item}" for item in exclude)
            continue
        else:
            out.append(line)
        i += 1
    return "\n".join(out) + "\n"


def _render_main_tex(course_name: str) -> str:
    text = (TEMPLATES / "main.tex").read_text(encoding="utf-8")
    return text.replace("{{COURSE_NAME}}", course_name)


def _render_courses_yml_entry(course_id: str, course_name: str, repo: str, visibility: str,
                               aliases: list[str], drive_folder: str, status: str) -> str:
    lines = [
        f"  {course_id}:",
        f"    course_name: {course_name}",
        f"    repository: {repo}",
        f"    visibility: {visibility}",
        "    aliases:",
        *[f"      - {a}" for a in aliases],
        f"    drive_folder: {drive_folder}",
        f"    status: {status}",
    ]
    return "\n".join(lines) + "\n"


def _dedup_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def main() -> int:
    args = _parse_args()
    _validate_course_id(args.id)
    _check_not_registered(args.id)

    drive_folder = args.drive_folder or args.name
    exclude = tuple(args.exclude) if args.exclude else _DEFAULT_EXCLUDE
    aliases = _dedup_keep_order([args.name, *args.alias])
    local_path = args.local_path.expanduser().resolve()

    writes: list[tuple[Path, str]] = []

    writes.append((
        local_path / "academic.yml",
        _render_academic_yml(args.id, args.name, drive_folder, exclude),
    ))
    for src_name, dest_rel in _VERBATIM_FILES.items():
        writes.append((local_path / dest_rel, (TEMPLATES / src_name).read_text(encoding="utf-8")))
    writes.append((local_path / "src/main.tex", _render_main_tex(args.name)))
    writes.append((local_path / "src/chapters/.gitkeep", ""))

    courses_entry = _render_courses_yml_entry(
        args.id, args.name, args.repo, args.visibility, aliases, drive_folder, args.status
    )

    if not args.force:
        existing = [str(path) for path, _ in writes if path.exists()]
        if existing:
            raise SystemExit(
                "既に存在するファイルがあります (--force で上書き):\n  "
                + "\n  ".join(existing)
            )

    print(f"[新規科目] {args.id} ({args.name}) -> {args.repo}")
    print(f"  local: {local_path}")
    for path, _ in writes:
        print(f"  write: {path}")
    print(f"  append: {COURSES_YML}")
    print(courses_entry)

    if args.dry_run:
        print("(--dry-run のため書き込みは行っていません)")
        return 0

    if not local_path.is_dir():
        raise SystemExit(f"{local_path} が存在しません。先に git clone してください。")

    for path, content in writes:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    courses_text = COURSES_YML.read_text(encoding="utf-8")
    new_courses_text = courses_text.rstrip("\n") + "\n\n" + courses_entry
    # 壊れたYAMLを書き戻さないための確認。
    parsed = yaml.safe_load(new_courses_text)
    if args.id not in (parsed.get("courses") or {}):
        raise SystemExit("courses.yml への追記結果が不正です (バグ)。書き込みを中止しました。")
    COURSES_YML.write_text(new_courses_text, encoding="utf-8")

    print("\n完了。次にやること:")
    print(f"  1. cd {local_path} && latexmk -lualatex -interaction=nonstopmode -halt-on-error src/main.tex で組版確認")
    print(f"  2. cd {local_path} && git add -A && git commit -m 'chore: scaffold {args.id}' && git push")
    print(f"  3. cd {ACADEMIC_INFRA_ROOT} && git add courses.yml && git commit -m 'chore: register {args.id}' && git push")
    print("  4. 章ができたら: python3 scripts/add_review_headers.py --repo-root " + str(local_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
