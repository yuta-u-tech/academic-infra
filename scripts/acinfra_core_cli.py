#!/usr/bin/env python3
"""Goal駆動型学習基盤 Core のCLI。設計書 §4 の `bin/academic-infra` 候補の先行実装。

    # Goal を作る
    python3 scripts/acinfra_core_cli.py goal create --id toeic-900 --title "TOEIC 900点"

    # 一覧・詳細
    python3 scripts/acinfra_core_cli.py goal list
    python3 scripts/acinfra_core_cli.py goal show toeic-900

    # 状態を変える
    python3 scripts/acinfra_core_cli.py goal update-status toeic-900 paused
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acinfra_core import goal  # noqa: E402
from acinfra_core.db import connect  # noqa: E402


def _cmd_goal_create(args: argparse.Namespace) -> int:
    with connect(args.db) as connection:
        created = goal.create_goal(
            connection,
            args.id,
            args.title,
            parent_goal_id=args.parent,
            target_value=args.target_value,
            current_value=args.current_value,
            deadline=args.deadline,
            priority=args.priority,
            evaluation_method=args.evaluation_method,
        )
    print(json.dumps(created.model_dump(), ensure_ascii=False, indent=2))
    return 0


def _cmd_goal_list(args: argparse.Namespace) -> int:
    with connect(args.db) as connection:
        goals = goal.list_goals(connection, status=args.status)
    print(json.dumps([g.model_dump() for g in goals], ensure_ascii=False, indent=2))
    return 0


def _cmd_goal_show(args: argparse.Namespace) -> int:
    with connect(args.db) as connection:
        found = goal.get_goal(connection, args.id)
    print(json.dumps(found.model_dump(), ensure_ascii=False, indent=2))
    return 0


def _cmd_goal_update_status(args: argparse.Namespace) -> int:
    with connect(args.db) as connection:
        updated = goal.update_goal_status(connection, args.id, args.status)
    print(json.dumps(updated.model_dump(), ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=None, help="SQLiteのパス（既定: ~/.academic-infra/core.db）")
    subparsers = parser.add_subparsers(dest="command", required=True)

    goal_parser = subparsers.add_parser("goal", help="Goal の CRUD")
    goal_subparsers = goal_parser.add_subparsers(dest="goal_command", required=True)

    create = goal_subparsers.add_parser("create", help="Goal を作る")
    create.add_argument("--id", required=True, dest="id")
    create.add_argument("--title", required=True)
    create.add_argument("--parent", help="親 Goal の goal_id")
    create.add_argument("--target-value")
    create.add_argument("--current-value")
    create.add_argument("--deadline", help="ISO8601 の日付")
    create.add_argument("--priority", type=int, default=3)
    create.add_argument("--evaluation-method")
    create.set_defaults(func=_cmd_goal_create)

    list_parser = goal_subparsers.add_parser("list", help="Goal 一覧")
    list_parser.add_argument("--status", choices=("active", "paused", "achieved", "abandoned"))
    list_parser.set_defaults(func=_cmd_goal_list)

    show = goal_subparsers.add_parser("show", help="Goal の詳細")
    show.add_argument("id")
    show.set_defaults(func=_cmd_goal_show)

    update_status = goal_subparsers.add_parser("update-status", help="Goal の状態を変える")
    update_status.add_argument("id")
    update_status.add_argument("status", choices=("active", "paused", "achieved", "abandoned"))
    update_status.set_defaults(func=_cmd_goal_update_status)

    args = parser.parse_args()
    try:
        return args.func(args)
    except (goal.GoalNotFoundError, goal.DuplicateGoalError, goal.InvalidGoalStatusError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
