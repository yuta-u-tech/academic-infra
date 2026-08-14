#!/usr/bin/env python3
"""TOEIC Reading CLI（Part 5・Part 7）。

`academic_audio_cli.py listening ...` と同じ形の日次更新フローを、音声を持たない
読解系（Part5空所補充・Part7読解）向けに用意したもの。科目リポジトリの内容には従属しない
（TOEICはどの科目の話者でもない、英語運用そのものの練習のため）。

    python3 scripts/toeic_reading_cli.py worksheet --items items.json --out .toeic-reading/sets/20260804-part5
    python3 scripts/toeic_reading_cli.py publish --pdf .toeic-reading/sets/20260804-part5/worksheet.pdf --dry-run

    # 同じ items.json を acenglish の学習ループ（attempt/skill_state）へ取り込む
    python3 scripts/toeic_reading_cli.py ingest --items items.json --set-id 20260804

    # Part7（読解）。items.json は passages グルーピング形（english/prompts/reading-part7.md参照）
    python3 scripts/toeic_reading_cli.py worksheet-part7 --items items.json --out .toeic-reading/sets/20260805-part7
    python3 scripts/toeic_reading_cli.py ingest-part7 --items items.json --set-id 20260805
    python3 scripts/toeic_reading_cli.py publish --pdf .toeic-reading/sets/20260805-part7/worksheet.pdf --folder-name TOEIC/reading/part7
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acenglish.db import connect  # noqa: E402
from acenglish.fetch import import_toeic_part5, import_toeic_part7  # noqa: E402
from acenglish.items import GrammarItem  # noqa: E402
from acenglish.sources.toeic_part7 import load_part7_items  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from toeic_reading.render import build_pdf, render_md, render_reading_md, render_reading_tex, render_tex  # noqa: E402

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


def _shuffle_choices(item: dict) -> None:
    """1問内の選択肢の並びをシャッフルし、answer_index を追従させる（破壊的更新）。

    作問（Claude が items.json を手で書く）は正解をA(index 0)に置く癖が強く、
    2026-08-14時点の実績で文法233問中214問(92%)が正解Aだった。設問順のシャッフルだけ
    では選択肢内の位置は変わらないため、ここで機械的に矯正する。
    """
    choices = item.get("choices")
    answer_index = item.get("answer_index")
    if not choices or answer_index is None:
        return
    order = list(range(len(choices)))
    random.shuffle(order)
    item["choices"] = [choices[i] for i in order]
    item["answer_index"] = order.index(answer_index)


def _cmd_shuffle(args: argparse.Namespace) -> int:
    """items.json 内の設問順序と、各設問内の選択肢順序を機械的にシャッフルする。

    設問順序: 「通常30問＋苦手重点20問」は書く順序上どうしても前半/後半に分かれるが、
    出題順がそのまま前半＝通常・後半＝苦手重点だと分かってしまう
    （復習であることが構成から見えてしまう）。worksheet/ingest/Form作成の
    前に必ずこのコマンドで順序を崩す。review_id は順序に基づいて
    割り当てられるため、ingestより前に実行すること。

    選択肢順序: 作問側（Claude）は正解をAに置く癖が強く出るため、機械的に矯正する
    （2026-08-14に発覚。全期間で正解Aが92%に偏っていた）。
    """
    payload = json.loads(args.items.read_text(encoding="utf-8"))
    items = payload.get("items")
    if not items:
        raise SystemExit("items が空か、'items' キーがありません。")
    random.shuffle(items)
    for item in items:
        _shuffle_choices(item)
    payload["items"] = items

    out_path = args.out or args.items
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"shuffled": len(items), "out": str(out_path)}, ensure_ascii=False, indent=2))
    return 0


def _cmd_worksheet(args: argparse.Namespace) -> int:
    title, items = _load_items(args.items)
    args.out.mkdir(parents=True, exist_ok=True)
    tex_path = args.out / "worksheet.tex"
    tex_path.write_text(render_tex(title, items, form_url=args.form_url), encoding="utf-8")
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


def _cmd_shuffle_part7(args: argparse.Namespace) -> int:
    """items.json(passagesグルーピング形)の各設問の選択肢順序を機械的にシャッフルする。

    Part7には「通常＋苦手重点」の前半/後半構成が無いのでpassage/設問の出題順シャッフルは
    不要だが、選択肢内の正解位置の偏り(Part5で92%がAだった)はPart7でも同じ作問側の癖で
    起こりうるため、ここでも矯正する（2026-08-14）。
    """
    payload = json.loads(args.items.read_text(encoding="utf-8"))
    passages = payload.get("passages")
    if not passages:
        raise SystemExit("passages が空か、'passages' キーがありません。")
    question_count = 0
    for passage in passages:
        for question in passage.get("questions", []):
            _shuffle_choices(question)
            question_count += 1

    out_path = args.out or args.items
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"shuffled_questions": question_count, "out": str(out_path)}, ensure_ascii=False, indent=2))
    return 0


def _cmd_worksheet_part7(args: argparse.Namespace) -> int:
    title, passages = load_part7_items(args.items)
    args.out.mkdir(parents=True, exist_ok=True)
    question_count = sum(len(p.questions) for p in passages)
    tex_path = args.out / "worksheet.tex"
    tex_path.write_text(render_reading_tex(title, passages, form_url=args.form_url), encoding="utf-8")
    pdf_path = build_pdf(tex_path)
    md_path = args.out / "worksheet.md"
    md_path.write_text(render_reading_md(title, passages), encoding="utf-8")
    print(json.dumps(
        {
            "pdf": str(pdf_path),
            "md": str(md_path),
            "passages": len(passages),
            "questions": question_count,
        },
        ensure_ascii=False, indent=2))
    return 0


def _cmd_ingest_part7(args: argparse.Namespace) -> int:
    _title, passages = load_part7_items(args.items)
    question_count = sum(len(p.questions) for p in passages)
    with connect(args.db) as connection:
        imported = import_toeic_part7(connection, args.set_id, passages)
    print(json.dumps(
        {"set_id": args.set_id, "count": question_count, "imported": imported},
        ensure_ascii=False, indent=2))
    return 0


def _cmd_weak_points(args: argparse.Namespace) -> int:
    """直近の誤答（Part5）を point/pattern 付きで並べる。集計・分類はしない。

    「同じpointが何回出た」を数えても意味がない（pointは毎回違う文で新しく書かれるため、
    厳密には repeat しない）。代わりに誤答の生データ（どの文法項目・どのパターンで
    間違えたか）をそのまま並べて返すので、次にどのpoint/pattern/語彙ペアを重点的に
    再出題するかは Claude が読んで判断する。
    """
    with connect(args.db) as connection:
        rows = connection.execute(
            """
            SELECT a.review_id, a.created_at, a.error_cause, g.payload
            FROM attempt a
            JOIN generated_item g ON a.review_id = g.review_id
            WHERE a.correct = 0 AND a.review_id LIKE 'toeic.part5.%'
            ORDER BY a.created_at DESC
            LIMIT ?
            """,
            (args.limit,),
        ).fetchall()

    results = []
    for row in rows:
        payload = json.loads(row["payload"])
        results.append({
            "review_id": row["review_id"],
            "created_at": row["created_at"],
            "error_cause": row["error_cause"],
            "sentence": payload.get("sentence"),
            "choices": payload.get("choices"),
            "answer_index": payload.get("answer_index"),
            "point": payload.get("point"),
            "pattern": payload.get("pattern"),
            "pattern_note": payload.get("pattern_note"),
        })
    print(json.dumps({"count": len(results), "wrong_attempts": results}, ensure_ascii=False, indent=2))
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
    # まとめる（例: TOEIC/reading/part5 → TOEIC/reading/MDs）。partが増えても集約先は1つに
    # なるので、ファイル名の方に <日付>-<part>.md でpartを残す（例: 2026-08-05-part5.md）。
    md_path = args.pdf.with_suffix(".md")
    md_folder_names = [*folder_names[:-1], "MDs"] if len(folder_names) > 1 else ["MDs"]
    part_label = folder_names[-1] if folder_names else None
    md_drive_name = f"{today}-{part_label}.md" if part_label else f"{today}.md"
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

    shuffle = sub.add_parser(
        "shuffle", help="items.json の設問順序を機械的にシャッフルする（30+20構成を混ぜる用、ingestより前に実行）"
    )
    shuffle.add_argument("--items", type=Path, required=True)
    shuffle.add_argument("--out", type=Path, help="既定: --items を上書き")
    shuffle.set_defaults(func=_cmd_shuffle)

    worksheet = sub.add_parser("worksheet", help="items.json から問題冊子PDFを組む")
    worksheet.add_argument("--items", type=Path, required=True, help="GrammarItem 形式の items.json")
    worksheet.add_argument("--out", type=Path, required=True, help="出力先ディレクトリ")
    worksheet.add_argument(
        "--form-url", help="toeic_forms_cli.py create で作成済みの回答フォームURL（先にForm作成が必須）"
    )
    worksheet.set_defaults(func=_cmd_worksheet)

    ingest = sub.add_parser("ingest", help="items.json を acenglish の学習ループへ取り込む")
    ingest.add_argument("--items", type=Path, required=True, help="GrammarItem 形式の items.json")
    ingest.add_argument("--set-id", required=True, help="このセットの識別子（review_idに使う）")
    ingest.add_argument("--db", type=Path, default=None, help="既定: ~/.academic-english/english.db")
    ingest.set_defaults(func=_cmd_ingest)

    shuffle_part7 = sub.add_parser(
        "shuffle-part7", help="items.json（passages形）の各設問の選択肢順序を機械的にシャッフルする（Form作成より前に実行）"
    )
    shuffle_part7.add_argument("--items", type=Path, required=True)
    shuffle_part7.add_argument("--out", type=Path, help="既定: --items を上書き")
    shuffle_part7.set_defaults(func=_cmd_shuffle_part7)

    worksheet_part7 = sub.add_parser("worksheet-part7", help="items.json（passages形）から Part7 問題冊子PDFを組む")
    worksheet_part7.add_argument("--items", type=Path, required=True, help="passages グルーピング形の items.json")
    worksheet_part7.add_argument("--out", type=Path, required=True, help="出力先ディレクトリ")
    worksheet_part7.add_argument(
        "--form-url", help="toeic_forms_cli.py create で作成済みの回答フォームURL（先にForm作成が必須）"
    )
    worksheet_part7.set_defaults(func=_cmd_worksheet_part7)

    ingest_part7 = sub.add_parser("ingest-part7", help="items.json（passages形）を acenglish の学習ループへ取り込む")
    ingest_part7.add_argument("--items", type=Path, required=True, help="passages グルーピング形の items.json")
    ingest_part7.add_argument("--set-id", required=True, help="このセットの識別子（review_idに使う）")
    ingest_part7.add_argument("--db", type=Path, default=None, help="既定: ~/.academic-english/english.db")
    ingest_part7.set_defaults(func=_cmd_ingest_part7)

    weak_points = sub.add_parser("weak-points", help="Part5の直近の誤答を point/pattern 付きで並べる（集計はしない）")
    weak_points.add_argument("--limit", type=int, default=30, help="取得件数の上限（既定30）")
    weak_points.add_argument("--db", type=Path, default=None, help="既定: ~/.academic-english/english.db")
    weak_points.set_defaults(func=_cmd_weak_points)

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
