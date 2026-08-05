#!/usr/bin/env python3
"""TOEIC Reading CLI（現状 Part 5 のみ）。

`academic_audio_cli.py listening ...` と同じ形の日次更新フローを、音声を持たない
文法問題（空所補充）向けに用意したもの。科目リポジトリの内容には従属しない
（TOEICはどの科目の話者でもない、英語運用そのものの練習のため）。

    python3 scripts/toeic_reading_cli.py worksheet --items items.json --out .toeic-reading/sets/20260804-part5
    python3 scripts/toeic_reading_cli.py publish --pdf .toeic-reading/sets/20260804-part5/worksheet.pdf --dry-run

    # 同じ items.json を acenglish の学習ループ（attempt/skill_state）へ取り込む
    python3 scripts/toeic_reading_cli.py ingest --items items.json --set-id 20260804
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acenglish.db import connect  # noqa: E402
from acenglish.fetch import import_toeic_part5  # noqa: E402
from acenglish.items import GrammarItem  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from toeic_reading.render import build_pdf, render_md, render_tex  # noqa: E402

DEFAULT_DRIVE_FOLDER_NAME = "TOEIC/reading/part5"


def _load_items(path: Path) -> tuple[str, list[GrammarItem]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    title = payload.get("title") or f"Part5 {datetime.now(timezone.utc):%Y-%m-%d}"
    try:
        items = [GrammarItem.model_validate(entry) for entry in payload["items"]]
    except ValidationError as error:
        raise SystemExit(f"items の形式が不正です:\n{error}")
    if not items:
        raise SystemExit("items が空です。")
    return title, items


def _cmd_worksheet(args: argparse.Namespace) -> int:
    title, items = _load_items(args.items)
    args.out.mkdir(parents=True, exist_ok=True)
    tex_path = args.out / "worksheet.tex"
    tex_path.write_text(render_tex(title, items), encoding="utf-8")
    pdf_path = build_pdf(tex_path)
    # ChatGPTにfree-formで解かせる用。PDFと同じ内容をMarkdownでも並べておく
    # （Driveへは publish が一緒にアップロードする）。
    md_path = args.out / "worksheet.md"
    md_path.write_text(render_md(title, items), encoding="utf-8")
    print(json.dumps(
        {"pdf": str(pdf_path), "md": str(md_path), "count": len(items)}, ensure_ascii=False, indent=2
    ))
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    _title, items = _load_items(args.items)
    with connect(args.db) as connection:
        imported = import_toeic_part5(connection, args.set_id, items)
    print(json.dumps({"set_id": args.set_id, "count": len(items), "imported": imported}, ensure_ascii=False, indent=2))
    return 0


def _cmd_publish(args: argparse.Namespace) -> int:
    import _drive_common

    if not args.pdf.exists():
        raise FileNotFoundError(f"{args.pdf} がありません。先に worksheet を実行してください。")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    drive_name = args.name or f"{today}.pdf"
    folder_names = [part for part in args.folder_name.split("/") if part]
    drive_path = "/".join([*folder_names, drive_name])

    # ChatGPTが読むMarkdownはPDFと同じ場所に混ぜず、reading配下の兄弟フォルダ「MDs」へ
    # まとめる（例: TOEIC/reading/part5 → TOEIC/reading/MDs）。partが増えても集約先は1つ。
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

    worksheet = sub.add_parser("worksheet", help="items.json から問題冊子PDFを組む")
    worksheet.add_argument("--items", type=Path, required=True, help="GrammarItem 形式の items.json")
    worksheet.add_argument("--out", type=Path, required=True, help="出力先ディレクトリ")
    worksheet.set_defaults(func=_cmd_worksheet)

    ingest = sub.add_parser("ingest", help="items.json を acenglish の学習ループへ取り込む")
    ingest.add_argument("--items", type=Path, required=True, help="GrammarItem 形式の items.json")
    ingest.add_argument("--set-id", required=True, help="このセットの識別子（review_idに使う）")
    ingest.add_argument("--db", type=Path, default=None, help="既定: ~/.academic-english/english.db")
    ingest.set_defaults(func=_cmd_ingest)

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
