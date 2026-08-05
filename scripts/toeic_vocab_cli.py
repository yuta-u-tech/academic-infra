#!/usr/bin/env python3
"""TOEIC 単語テスト CLI（語彙MCQ、生成不要・冪等）。

TOEIC語彙（`acenglish_cli.py fetch-toeic` で取り込み済みの2,282語）から、
シャッフル済みの順序を状態として持ち回りながら1日分（既定100問）を切り出して
問題冊子PDFを組む。1サイクル（プール全体、約23日分）を出し切ったら自動的に
再シャッフルして次のサイクルへ入るため、「毎日ランダムだが同じサイクル内では
重複しない」出題になる。

    python3 scripts/toeic_vocab_cli.py build --count 100 --out .toeic-vocab/sets/20260806
    python3 scripts/toeic_vocab_cli.py publish --pdf .toeic-vocab/sets/20260806/worksheet.pdf
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acenglish.db import connect  # noqa: E402
from acenglish.vocab_quiz import build_choices, load_pool, next_batch  # noqa: E402
from toeic_reading.vocab_render import QuizQuestion, build_pdf, render_md, render_tex  # noqa: E402

DEFAULT_DRIVE_FOLDER_NAME = "TOEIC/vocabulary"


def _cmd_build(args: argparse.Namespace) -> int:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    title = args.title or f"語彙テスト {today}"

    with connect(args.db) as connection:
        pool = load_pool(connection)
        if not pool:
            raise SystemExit(
                "語彙プールが空です。先に `acenglish_cli.py fetch-toeic` で取り込んでください。"
            )
        batch, state = next_batch(pool, args.count, home=args.home)

    questions = []
    for entry in batch:
        choices, answer_index = build_choices(entry, pool)
        questions.append(QuizQuestion(
            review_id=entry.review_id,
            word=entry.word,
            choices=choices,
            answer_index=answer_index,
            meaning=entry.meaning,
            example=entry.example,
        ))

    args.out.mkdir(parents=True, exist_ok=True)
    items_path = args.out / "items.json"
    items_path.write_text(
        json.dumps(
            {
                "title": title,
                "cycle": state["cycle"],
                "questions": [
                    {
                        "review_id": q.review_id,
                        "word": q.word,
                        "choices": q.choices,
                        "answer_index": q.answer_index,
                        "meaning": q.meaning,
                        "example": q.example,
                    }
                    for q in questions
                ],
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )

    tex_path = args.out / "worksheet.tex"
    tex_path.write_text(render_tex(title, questions), encoding="utf-8")
    pdf_path = build_pdf(tex_path)
    md_path = args.out / "worksheet.md"
    md_path.write_text(render_md(title, questions), encoding="utf-8")

    print(json.dumps(
        {
            "pdf": str(pdf_path),
            "md": str(md_path),
            "items": str(items_path),
            "count": len(questions),
            "cycle": state["cycle"],
            "pool_size": len(pool),
        },
        ensure_ascii=False, indent=2))
    return 0


def _cmd_publish(args: argparse.Namespace) -> int:
    import _drive_common

    if not args.pdf.exists():
        raise FileNotFoundError(f"{args.pdf} がありません。先に build を実行してください。")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    drive_name = args.name or f"{today}.pdf"
    folder_names = [part for part in args.folder_name.split("/") if part]
    drive_path = "/".join([*folder_names, drive_name])

    md_path = args.pdf.with_suffix(".md")
    md_folder_names = [*folder_names[:-1], "MDs"] if len(folder_names) > 1 else ["MDs"]
    md_drive_name = f"{today}.md"
    md_drive_path = "/".join([*md_folder_names, md_drive_name]) if md_path.exists() else None

    if args.dry_run:
        print(json.dumps(
            {
                "dry_run": True,
                "drive_path": drive_path,
                "local": str(args.pdf),
                "md_drive_path": md_drive_path,
                "md_local": str(md_path) if md_path.exists() else None,
            },
            ensure_ascii=False, indent=2))
        return 0

    credentials = _drive_common.resolve_credentials()
    parent_id = args.parent_id or credentials.get("GDRIVE_PARENT_FOLDER_ID", "")
    if not parent_id:
        raise ValueError("--parent-id か GDRIVE_PARENT_FOLDER_ID が必要です。")

    service = _drive_common.build_service(credentials)
    folder_id = parent_id
    for name in folder_names:
        folder_id = _drive_common.ensure_folder(service, folder_id, name)
    file_id = _drive_common.upload_file(service, folder_id, args.pdf, "application/pdf", name=drive_name)

    md_file_id = None
    if md_path.exists():
        md_folder_id = parent_id
        for name in md_folder_names:
            md_folder_id = _drive_common.ensure_folder(service, md_folder_id, name)
        md_file_id = _drive_common.upload_file(service, md_folder_id, md_path, "text/markdown", name=md_drive_name)

    print(json.dumps(
        {
            "drive_path": drive_path,
            "file_id": file_id,
            "url": f"https://drive.google.com/file/d/{file_id}/view",
            "md_drive_path": md_drive_path,
            "md_file_id": md_file_id,
            "md_url": f"https://drive.google.com/file/d/{md_file_id}/view" if md_file_id else None,
        },
        ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="今日分の語彙テストPDFを組む（状態を1回分進める）")
    build.add_argument("--count", type=int, default=100, help="1回の出題数（既定100）")
    build.add_argument("--out", type=Path, required=True, help="出力先ディレクトリ")
    build.add_argument("--title", help="既定: 語彙テスト <日付>")
    build.add_argument("--db", type=Path, default=None, help="既定: ~/.academic-english/english.db")
    build.add_argument("--home", type=Path, default=None, help="状態ファイルの置き場所。既定: ~/.academic-english")
    build.set_defaults(func=_cmd_build)

    publish = sub.add_parser("publish", help="問題冊子PDFを Drive へ上げる")
    publish.add_argument("--pdf", type=Path, required=True)
    publish.add_argument("--folder-name", default=DEFAULT_DRIVE_FOLDER_NAME, help="Drive 上のフォルダパス（/ 区切り）")
    publish.add_argument("--name", help="Drive 上のファイル名（既定: <当日の日付>.pdf）")
    publish.add_argument("--parent-id", help="既定は GDRIVE_PARENT_FOLDER_ID")
    publish.add_argument("--dry-run", action="store_true")
    publish.set_defaults(func=_cmd_publish)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
