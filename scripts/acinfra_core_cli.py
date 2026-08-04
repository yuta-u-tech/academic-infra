#!/usr/bin/env python3
"""Goal駆動型学習基盤 Core のCLI。設計書 §4 の `bin/academic-infra` 候補の先行実装。

    # Goal を作る
    python3 scripts/acinfra_core_cli.py goal create --id toeic-900 --title "TOEIC 900点"

    # 一覧・詳細
    python3 scripts/acinfra_core_cli.py goal list
    python3 scripts/acinfra_core_cli.py goal show toeic-900

    # 状態を変える
    python3 scripts/acinfra_core_cli.py goal update-status toeic-900 paused

    # Domain Plugin の Competency を登録する
    python3 scripts/acinfra_core_cli.py competency register --goal toeic-900 --domain toeic
    python3 scripts/acinfra_core_cli.py competency list --goal toeic-900

    # acenglish の Evidence/Mastery を読んで要約する（Core には保存しない）
    python3 scripts/acinfra_core_cli.py competency mastery --goal toeic-900
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acenglish.db import connect as connect_acenglish  # noqa: E402
from acinfra_core import competency, goal  # noqa: E402
from acinfra_core.db import connect  # noqa: E402
from acinfra_core.plugins.toeic import ToeicPlugin  # noqa: E402

DOMAIN_PLUGINS = {"toeic": ToeicPlugin}


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


def _cmd_competency_register(args: argparse.Namespace) -> int:
    plugin_cls = DOMAIN_PLUGINS[args.domain]
    with connect_acenglish(args.english_db) as acenglish_connection:
        plugin = plugin_cls(acenglish_connection)
        with connect(args.db) as connection:
            registered = competency.register_domain_competencies(connection, args.goal, plugin)
    print(json.dumps([c.model_dump() for c in registered], ensure_ascii=False, indent=2))
    return 0


def _cmd_competency_list(args: argparse.Namespace) -> int:
    with connect(args.db) as connection:
        competencies = competency.list_competencies(connection, args.goal)
    print(json.dumps([c.model_dump() for c in competencies], ensure_ascii=False, indent=2))
    return 0


def _cmd_competency_mastery(args: argparse.Namespace) -> int:
    with connect(args.db) as connection:
        competencies = competency.list_competencies(connection, args.goal)

    by_domain: dict[str, list] = {}
    for item in competencies:
        by_domain.setdefault(item.domain_id, []).append(item)

    report = []
    with connect_acenglish(args.english_db) as acenglish_connection:
        for domain_id, items in by_domain.items():
            plugin_cls = DOMAIN_PLUGINS.get(domain_id)
            if plugin_cls is None:
                for item in items:
                    report.append({"competency_id": item.competency_id, "note": f"未対応のdomain_id: {domain_id}"})
                continue
            plugin = plugin_cls(acenglish_connection)
            templates = {t.competency_id: t for t in plugin.competencies()}
            summaries = plugin.mastery_summary(
                [templates[item.competency_id] for item in items if item.competency_id in templates]
            )
            for item in items:
                summary = summaries.get(item.competency_id)
                if summary is None:
                    report.append({"competency_id": item.competency_id, "note": "Plugin未定義のCompetency"})
                    continue
                template = templates[item.competency_id]
                hint = plugin.resource_gap_hint(template, summary)
                entry = summary.model_dump()
                entry["title"] = item.title
                entry["resource_gap_hint"] = hint.model_dump() if hint else None
                report.append(entry)

    print(json.dumps(report, ensure_ascii=False, indent=2))
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

    competency_parser = subparsers.add_parser("competency", help="Domain Plugin の Competency")
    competency_subparsers = competency_parser.add_subparsers(dest="competency_command", required=True)

    register = competency_subparsers.add_parser("register", help="Domain Plugin の Competency を Goal に登録する")
    register.add_argument("--goal", required=True)
    register.add_argument("--domain", required=True, choices=tuple(DOMAIN_PLUGINS))
    register.add_argument("--english-db", type=Path, default=None, dest="english_db")
    register.set_defaults(func=_cmd_competency_register)

    competency_list = competency_subparsers.add_parser("list", help="Goal に登録された Competency 一覧")
    competency_list.add_argument("--goal", required=True)
    competency_list.set_defaults(func=_cmd_competency_list)

    mastery = competency_subparsers.add_parser(
        "mastery", help="acenglish の Evidence/Mastery を読んで要約する（Core には保存しない）"
    )
    mastery.add_argument("--goal", required=True)
    mastery.add_argument("--english-db", type=Path, default=None, dest="english_db")
    mastery.set_defaults(func=_cmd_competency_mastery)

    args = parser.parse_args()
    try:
        return args.func(args)
    except (goal.GoalNotFoundError, goal.DuplicateGoalError, goal.InvalidGoalStatusError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
