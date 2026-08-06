#!/usr/bin/env python3
"""統計検定準1級 学習ループCLI（10日間の集中演習用・最小構成）。

TOEICのacenglishと違い、SM-2間隔反復やLaTeX冊子・Drive publishは持たない。
問題は Claude が `toukei/prompts/generation.md` の形式で items.json を書き、
このCLIで取り込み・出題・採点するだけ。

    # 生成した問題を取り込む（competency_idは4分野のいずれか）
    python3 scripts/toukei_cli.py ingest --file items.json --competency toukei.probability_distribution --set-id 20260806

    # 出題（ターミナルで解答。誤答が多い問題・未回答の問題を優先して出す）
    python3 scripts/toukei_cli.py quiz --count 10
    python3 scripts/toukei_cli.py quiz --competency toukei.statistical_inference --count 10

    # 習熟度の確認（Core の `competency mastery` からも同じ値が見える）
    python3 scripts/toukei_cli.py status

    # 同じ優先順位（未回答→誤答が多い順）で選んだ問題をPDFに組む。
    # 2026-08-06: 出典（statisticsschool.com）の解説品質に問題があったため、119問全てを
    # Codexでゼロから生成し直した経緯があり、既定では構造化フィールドから直接LaTeXを組む
    # （出典.texへの依存はない。旧・出典スライス経路はsource_numberを持つ行にのみ残っている）。
    python3 scripts/toukei_cli.py worksheet --competency toukei.probability_distribution --count 15 --out .toukei-worksheets/20260806

    # Driveへアップロード
    python3 scripts/toukei_cli.py publish --pdf .toukei-worksheets/20260806/worksheet.pdf
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from toukei_study.db import connect  # noqa: E402
from toukei_study.render import GENERATED_PREAMBLE  # noqa: E402
from toukei_study.render import build_pdf as render_build_pdf  # noqa: E402
from toukei_study.render import (  # noqa: E402
    build_generated_block,
    build_worksheet_tex,
    extract_preamble,
    extract_raw_blocks,
)
from toukei_study.study import ingest_problems, next_batch, record_attempt, status  # noqa: E402

COMPETENCY_IDS = (
    "toukei.probability_distribution",
    "toukei.statistical_inference",
    "toukei.multivariate_analysis",
    "toukei.applications",
)

COMPETENCY_TITLES = {
    "toukei.probability_distribution": "確率と確率分布",
    "toukei.statistical_inference": "統計的推測",
    "toukei.multivariate_analysis": "多変量解析法",
    "toukei.applications": "種々の応用",
}

DEFAULT_SOURCE_TEX = (
    Path.home() / "Desktop" / "Statistical_Society_Certificate_pre_1" / "problems_statistics_applied.tex"
)

DEFAULT_DRIVE_FOLDER_NAME = "統計検定準1級"


def _cmd_ingest(args: argparse.Namespace) -> int:
    payload = json.loads(args.file.read_text(encoding="utf-8"))
    items = payload["items"] if isinstance(payload, dict) else payload
    with connect(args.db) as connection:
        inserted = ingest_problems(connection, args.set_id, args.competency, items)
    print(json.dumps({"competency": args.competency, "set_id": args.set_id, "inserted": inserted}, ensure_ascii=False, indent=2))
    return 0


def _cmd_quiz(args: argparse.Namespace) -> int:
    with connect(args.db) as connection:
        problems = next_batch(connection, args.competency, args.count)
        if not problems:
            print("出題できる問題がありません。先に ingest してください。", file=sys.stderr)
            return 1

        correct_count = 0
        for index, problem in enumerate(problems, start=1):
            print(f"\n[{index}/{len(problems)}] ({problem.competency_id})")
            print(problem.question)
            for choice_index, choice in enumerate(problem.choices):
                print(f"  {choice_index + 1}. {choice}")
            raw = input("答え(番号): ").strip()
            try:
                chosen_index = int(raw) - 1
            except ValueError:
                chosen_index = -1
            correct = record_attempt(connection, problem, chosen_index)
            if correct:
                correct_count += 1
                print("○ 正解")
            else:
                correct_answer = problem.choices[problem.answer_index]
                print(f"× 不正解（正解: {problem.answer_index + 1}. {correct_answer}）")
            print(f"解説: {problem.explanation}")

        print(f"\n結果: {correct_count}/{len(problems)}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    with connect(args.db) as connection:
        report = status(connection)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def _cmd_worksheet(args: argparse.Namespace) -> int:
    with connect(args.db) as connection:
        selected = next_batch(connection, args.competency, args.count)
    if not selected:
        print("出題できる問題がありません。先に ingest してください。", file=sys.stderr)
        return 1

    # source_numberを持つ問題（出典.texから切り出す旧経路）とCodex生成分（構造化フィールドから
    # 直接組む既定経路）が混在しうるので、両方サポートする。
    needs_source = any(p.source_number is not None for p in selected)
    blocks: list[str] = []
    if needs_source and args.tex.exists():
        blocks_by_number = extract_raw_blocks(args.tex)
    else:
        blocks_by_number = {}

    for index, problem in enumerate(selected, start=1):
        if problem.source_number is not None and problem.source_number in blocks_by_number:
            blocks.append(blocks_by_number[problem.source_number])
        else:
            blocks.append(
                build_generated_block(index, problem.question, problem.choices, problem.answer_index, problem.explanation)
            )

    preamble = extract_preamble(args.tex) if (needs_source and args.tex.exists()) else GENERATED_PREAMBLE
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    title = f"{COMPETENCY_TITLES.get(args.competency, args.competency)} {today}"
    tex_content = build_worksheet_tex(preamble, title, blocks)

    args.out.mkdir(parents=True, exist_ok=True)
    tex_path = args.out / "worksheet.tex"
    tex_path.write_text(tex_content, encoding="utf-8")
    pdf_path = render_build_pdf(tex_path)
    print(json.dumps(
        {"pdf": str(pdf_path), "count": len(blocks), "competency": args.competency}, ensure_ascii=False, indent=2
    ))
    return 0


def _cmd_publish(args: argparse.Namespace) -> int:
    import _drive_common

    if not args.pdf.exists():
        raise FileNotFoundError(f"{args.pdf} がありません。先に worksheet を実行してください。")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    drive_name = args.name or f"{today}.pdf"
    folder_names = [part for part in args.folder_name.split("/") if part]
    drive_path = "/".join([*folder_names, drive_name])

    if args.dry_run:
        print(json.dumps({"dry_run": True, "drive_path": drive_path, "local": str(args.pdf)},
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

    print(json.dumps(
        {
            "drive_path": drive_path,
            "file_id": file_id,
            "url": f"https://drive.google.com/file/d/{file_id}/view",
        },
        ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=None, help="SQLiteのパス（既定: ~/.academic-toukei/toukei.db）")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="生成済み問題を取り込む")
    ingest.add_argument("--file", type=Path, required=True)
    ingest.add_argument("--competency", required=True, choices=COMPETENCY_IDS)
    ingest.add_argument("--set-id", required=True, dest="set_id")
    ingest.set_defaults(func=_cmd_ingest)

    quiz = subparsers.add_parser("quiz", help="ターミナルで出題・採点する")
    quiz.add_argument("--competency", choices=COMPETENCY_IDS, default=None)
    quiz.add_argument("--count", type=int, default=10)
    quiz.set_defaults(func=_cmd_quiz)

    status_parser = subparsers.add_parser("status", help="Competency別の習熟度を見る")
    status_parser.set_defaults(func=_cmd_status)

    worksheet = subparsers.add_parser(
        "worksheet", help="出典.texから毎回切り出し直して問題冊子PDFを組む"
    )
    worksheet.add_argument("--competency", required=True, choices=COMPETENCY_IDS)
    worksheet.add_argument("--count", type=int, default=15)
    worksheet.add_argument("--out", type=Path, required=True)
    worksheet.add_argument("--tex", type=Path, default=DEFAULT_SOURCE_TEX)
    worksheet.set_defaults(func=_cmd_worksheet)

    publish = subparsers.add_parser("publish", help="問題冊子PDFをDriveへ上げる")
    publish.add_argument("--pdf", type=Path, required=True)
    publish.add_argument("--folder-name", default=DEFAULT_DRIVE_FOLDER_NAME, help="Drive上のフォルダパス（/区切り）")
    publish.add_argument("--name", help="Drive上のファイル名（既定: <当日の日付>.pdf）")
    publish.add_argument("--parent-id", help="既定は GDRIVE_PARENT_FOLDER_ID")
    publish.add_argument("--dry-run", action="store_true")
    publish.set_defaults(func=_cmd_publish)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
