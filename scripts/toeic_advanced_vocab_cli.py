#!/usr/bin/env python3
"""『TOEIC上級単語.pdf』OCR取り込み用ステージングDB CLI（Issue #9）。

本番 `english.db` とはファイルごと独立した `staging-toeic-advanced.db` を操作する。
ここでの承認（approved）は「本番へマージしてよい」の意思表示に過ぎず、実際の
`generated_item` への書き込み（マージ処理）はまだ実装していない（Issue #9 の非スコープ）。

    # DBを初期化するだけ（テーブルが無ければ作る。既にあれば何もしない）
    python3 scripts/toeic_advanced_vocab_cli.py init

    # OCR結果をJSON Lines（1行1語、word/meaning必須、page_number必須）から一括投入
    python3 scripts/toeic_advanced_vocab_cli.py import-jsonl --file ocr-page012.jsonl

    # 手動で1件追加（OCRパイプライン未整備の段階で少数だけ試す時など）
    python3 scripts/toeic_advanced_vocab_cli.py add --page-number 12 --word "aberration" \\
        --meaning "逸脱、異常" --part-of-speech n. --example "a temporary aberration"

    # レビュー待ち一覧
    python3 scripts/toeic_advanced_vocab_cli.py list --status pending

    # レビュー結果を記録
    python3 scripts/toeic_advanced_vocab_cli.py review --id 3 --status approved
    python3 scripts/toeic_advanced_vocab_cli.py review --id 4 --status rejected --note "OCR誤読、原本で判読不能"

    # 件数サマリ
    python3 scripts/toeic_advanced_vocab_cli.py stats
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acenglish.toeic_advanced_db import (  # noqa: E402
    add_candidate,
    connect,
    list_candidates,
    set_review,
    stats as db_stats,
)


def _cmd_init(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    connection.close()
    print(json.dumps({"initialized": True}, ensure_ascii=False))
    return 0


def _cmd_add(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    candidate_id = add_candidate(
        connection,
        page_number=args.page_number,
        word=args.word,
        meaning=args.meaning,
        part_of_speech=args.part_of_speech,
        example=args.example,
        ocr_confidence=args.ocr_confidence,
    )
    connection.close()
    print(json.dumps({"id": candidate_id}, ensure_ascii=False))
    return 0


def _cmd_import_jsonl(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    imported = []
    with args.file.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            for required in ("page_number", "word", "meaning"):
                if required not in row:
                    raise SystemExit(
                        f"{args.file}:{line_number}: 必須キー '{required}' がありません。"
                    )
            candidate_id = add_candidate(
                connection,
                page_number=row["page_number"],
                word=row["word"],
                meaning=row["meaning"],
                part_of_speech=row.get("part_of_speech"),
                example=row.get("example"),
                ocr_confidence=row.get("ocr_confidence"),
            )
            imported.append(candidate_id)
    connection.close()
    print(json.dumps({"imported": len(imported), "ids": imported}, ensure_ascii=False))
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    rows = list_candidates(connection, status=args.status)
    connection.close()
    print(json.dumps([dict(row) for row in rows], ensure_ascii=False, indent=2))
    return 0


def _cmd_review(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    set_review(
        connection,
        args.id,
        status=args.status,
        review_note=args.note,
        dup_of_review_id=args.dup_of_review_id,
    )
    connection.close()
    print(json.dumps({"id": args.id, "status": args.status}, ensure_ascii=False))
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    result = db_stats(connection)
    connection.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--db", type=Path, default=None, help="既定は ~/.academic-english/staging-toeic-advanced.db")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="DBを初期化する").set_defaults(func=_cmd_init)

    add = sub.add_parser("add", help="OCR候補を1件追加")
    add.add_argument("--page-number", type=int, required=True)
    add.add_argument("--word", required=True)
    add.add_argument("--meaning", required=True)
    add.add_argument("--part-of-speech")
    add.add_argument("--example")
    add.add_argument("--ocr-confidence", type=float)
    add.set_defaults(func=_cmd_add)

    import_jsonl = sub.add_parser("import-jsonl", help="JSON Linesから一括投入")
    import_jsonl.add_argument("--file", type=Path, required=True)
    import_jsonl.set_defaults(func=_cmd_import_jsonl)

    list_cmd = sub.add_parser("list", help="候補一覧")
    list_cmd.add_argument("--status", choices=("pending", "approved", "rejected", "merged"))
    list_cmd.set_defaults(func=_cmd_list)

    review = sub.add_parser("review", help="レビュー結果を記録")
    review.add_argument("--id", type=int, required=True)
    review.add_argument("--status", choices=("approved", "rejected"), required=True)
    review.add_argument("--note")
    review.add_argument("--dup-of-review-id", help="本番プールと重複と判定した場合、その review_id")
    review.set_defaults(func=_cmd_review)

    sub.add_parser("stats", help="ステータス別件数").set_defaults(func=_cmd_stats)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
