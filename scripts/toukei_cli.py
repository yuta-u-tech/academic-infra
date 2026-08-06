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
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from toukei_study.db import connect  # noqa: E402
from toukei_study.study import ingest_problems, next_batch, record_attempt, status  # noqa: E402

COMPETENCY_IDS = (
    "toukei.probability_distribution",
    "toukei.statistical_inference",
    "toukei.multivariate_analysis",
    "toukei.applications",
)


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

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
