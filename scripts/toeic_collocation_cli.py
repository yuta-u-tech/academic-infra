#!/usr/bin/env python3
"""金フレ(study-forge由来のTOEIC語彙DB)からコロケーション暗記動画を作るための
生産ラインCLI。

    # まだコロケーション未執筆の語をN件取り出す
    python3 scripts/toeic_collocation_cli.py candidates --limit 20 --out /tmp/req.json

    # Claudeが書いた結果を取り込む(collocations_v2としてDBへ永続化)
    python3 scripts/toeic_collocation_cli.py ingest --file /tmp/result.json

    # 未処理の残り件数を見る
    python3 scripts/toeic_collocation_cli.py status
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acenglish.db import connect  # noqa: E402


def _iter_all_rows(connection):
    rows = connection.execute(
        "SELECT review_id, payload FROM generated_item WHERE kind = 'vocab' AND review_id LIKE 'toeic.%' "
        "ORDER BY review_id"
    ).fetchall()
    for review_id, payload_raw in rows:
        yield review_id, json.loads(payload_raw)


def _cmd_status(args: argparse.Namespace) -> int:
    with connect(args.db) as connection:
        total = 0
        done = 0
        for _review_id, payload in _iter_all_rows(connection):
            total += 1
            if payload.get("collocations_v2"):
                done += 1
    print(f"合計: {total}語 / 執筆済み: {done}語 / 未処理: {total - done}語")
    return 0


def _cmd_candidates(args: argparse.Namespace) -> int:
    with connect(args.db) as connection:
        picked = []
        for review_id, payload in _iter_all_rows(connection):
            if payload.get("collocations_v2"):
                continue
            if args.deck and not review_id.startswith(f"toeic.{args.deck}."):
                continue
            picked.append(
                {
                    "review_id": review_id,
                    "word": payload["word"],
                    "meaning": payload["meaning"],
                    "part_of_speech": payload.get("part_of_speech"),
                    "existing_example": payload.get("example"),
                }
            )
            if len(picked) >= args.limit:
                break
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(picked, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"未執筆の候補 {len(picked)}件を書き出し: {args.out}")
    return 0


_REQUIRED_ITEM_FIELDS = ("collocations", "example_en", "example_ja")
_REQUIRED_COLLOCATION_FIELDS = ("phrase", "phrase_ja")


class IngestError(ValueError):
    pass


def _validate_result(result: dict) -> None:
    for review_id, content in result.items():
        missing = [key for key in _REQUIRED_ITEM_FIELDS if key not in content]
        if missing:
            raise IngestError(f"{review_id}: {', '.join(missing)} がありません。")
        collocations = content["collocations"]
        if not isinstance(collocations, list) or not (1 <= len(collocations) <= 4):
            raise IngestError(f"{review_id}: collocationsは1〜4件のリストにしてください。")
        for c in collocations:
            missing_c = [key for key in _REQUIRED_COLLOCATION_FIELDS if key not in c]
            if missing_c:
                raise IngestError(f"{review_id}: collocationsの要素に{', '.join(missing_c)}がありません。")


def _cmd_ingest(args: argparse.Namespace) -> int:
    result = json.loads(args.file.read_text(encoding="utf-8"))
    _validate_result(result)
    with connect(args.db) as connection:
        for review_id, content in result.items():
            row = connection.execute(
                "SELECT payload FROM generated_item WHERE review_id = ?", (review_id,)
            ).fetchone()
            if row is None:
                raise IngestError(f"{review_id} が generated_item に見つかりません。")
            payload = json.loads(row[0])
            payload["collocations_v2"] = content["collocations"]
            connection.execute(
                "UPDATE generated_item SET payload = ? WHERE review_id = ?",
                (json.dumps(payload, ensure_ascii=False), review_id),
            )
        connection.commit()
    print(f"{len(result)}語のcollocationsを永続化しました。")
    return 0


def _cmd_batch(args: argparse.Namespace) -> int:
    """render用に、既にcollocations_v2が入っている語をN件まとめて書き出す
    (word/meaning/part_of_speech/collocations_v2)。exampleは持たないので
    render時は別途Claudeが書いたexampleファイルとマージする(video-build手順参照)。
    """
    with connect(args.db) as connection:
        picked = []
        for review_id, payload in _iter_all_rows(connection):
            if not payload.get("collocations_v2"):
                continue
            if args.deck and not review_id.startswith(f"toeic.{args.deck}."):
                continue
            picked.append(
                {
                    "review_id": review_id,
                    "word": payload["word"],
                    "meaning": payload["meaning"],
                    "part_of_speech": payload.get("part_of_speech"),
                    "collocations_v2": payload["collocations_v2"],
                }
            )
    if args.offset:
        picked = picked[args.offset :]
    if args.limit:
        picked = picked[: args.limit]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(picked, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"執筆済みの{len(picked)}語を書き出し: {args.out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status", help="執筆済み/未処理の件数を見る")
    status.set_defaults(func=_cmd_status)

    candidates = subparsers.add_parser("candidates", help="コロケーション未執筆の語を取り出す")
    candidates.add_argument("--limit", type=int, default=20)
    candidates.add_argument("--deck", help="words1-400/words401-700/.../supplement1〜3 のいずれか。省略時は全デッキ")
    candidates.add_argument("--out", type=Path, required=True)
    candidates.set_defaults(func=_cmd_candidates)

    ingest = subparsers.add_parser("ingest", help="Claudeが書いたcollocationsをDBへ永続化する")
    ingest.add_argument("--file", type=Path, required=True)
    ingest.set_defaults(func=_cmd_ingest)

    batch = subparsers.add_parser("batch", help="動画化用に、執筆済みの語をまとめて書き出す")
    batch.add_argument("--deck", help="words1-400/.../supplement1〜3 のいずれか。省略時は全デッキ")
    batch.add_argument("--offset", type=int, default=0)
    batch.add_argument("--limit", type=int)
    batch.add_argument("--out", type=Path, required=True)
    batch.set_defaults(func=_cmd_batch)

    args = parser.parse_args()
    try:
        return args.func(args)
    except IngestError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
