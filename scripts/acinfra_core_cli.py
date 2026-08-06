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
    # 不足が見つかった Competency を resource_requirement として起票する
    python3 scripts/acinfra_core_cli.py competency mastery --goal toeic-900 --open-requirements

    # 教材台帳
    python3 scripts/acinfra_core_cli.py resource register --goal toeic-900 --id vol8 \
        --title "TOEIC公式問題集8" --kind book
    python3 scripts/acinfra_core_cli.py resource list --goal toeic-900

    # 不足診断
    python3 scripts/acinfra_core_cli.py requirement list --goal toeic-900
    python3 scripts/acinfra_core_cli.py requirement resolve req-id
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acenglish.db import connect as connect_acenglish  # noqa: E402
from acinfra_core import competency, goal, resource  # noqa: E402
from acinfra_core import resource_requirement as rr  # noqa: E402
from acinfra_core.db import connect  # noqa: E402
from acinfra_core.plugins.toeic import ToeicPlugin  # noqa: E402
from acinfra_core.plugins.toukei import ToukeiPlugin  # noqa: E402
from toukei_study.db import connect as connect_toukei  # noqa: E402

DOMAIN_PLUGINS = {"toeic": ToeicPlugin, "toukei": ToukeiPlugin}
# Domain Pluginごとに個人データDBが違う（acenglishのenglish.db / toukei_studyのtoukei.db）ので、
# `--english-db` 一本ではなくdomain_idからconnect関数を引く。
DOMAIN_CONNECTORS = {"toeic": connect_acenglish, "toukei": connect_toukei}


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
    connector = DOMAIN_CONNECTORS[args.domain]
    domain_db = args.english_db if args.domain == "toeic" else args.domain_db
    with connector(domain_db) as domain_connection:
        plugin = plugin_cls(domain_connection)
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
        for domain_id, items in by_domain.items():
            plugin_cls = DOMAIN_PLUGINS.get(domain_id)
            connector = DOMAIN_CONNECTORS.get(domain_id)
            if plugin_cls is None or connector is None:
                for item in items:
                    report.append(
                        {"competency_id": item.competency_id, "note": f"未対応のdomain_id: {domain_id}"}
                    )
                continue
            domain_db = args.english_db if domain_id == "toeic" else args.domain_db
            with connector(domain_db) as domain_connection:
                plugin = plugin_cls(domain_connection)
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
                    if hint is not None and args.open_requirements:
                        requirement_id = f"auto.{item.competency_id}"
                        if rr.get_requirement(connection, requirement_id, required=False) is None:
                            rr.open_requirement_from_gap_hint(connection, args.goal, requirement_id, hint)
                        entry["requirement_id"] = requirement_id
                    report.append(entry)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def _cmd_resource_register(args: argparse.Namespace) -> int:
    with connect(args.db) as connection:
        created = resource.register_resource(
            connection, args.goal, args.id, args.title, args.kind,
            location=args.location, authority=args.authority,
        )
    print(json.dumps(created.model_dump(), ensure_ascii=False, indent=2))
    return 0


def _cmd_resource_list(args: argparse.Namespace) -> int:
    with connect(args.db) as connection:
        resources = resource.list_resources(connection, args.goal, status=args.status)
    print(json.dumps([r.model_dump() for r in resources], ensure_ascii=False, indent=2))
    return 0


def _cmd_resource_update_status(args: argparse.Namespace) -> int:
    with connect(args.db) as connection:
        updated = resource.update_resource_status(connection, args.id, args.status)
    print(json.dumps(updated.model_dump(), ensure_ascii=False, indent=2))
    return 0


def _cmd_requirement_list(args: argparse.Namespace) -> int:
    with connect(args.db) as connection:
        requirements = rr.list_requirements(connection, args.goal, status=args.status)
    print(json.dumps([r.model_dump() for r in requirements], ensure_ascii=False, indent=2))
    return 0


def _cmd_requirement_resolve(args: argparse.Namespace) -> int:
    with connect(args.db) as connection:
        updated = rr.update_requirement_status(connection, args.id, "resolved")
    print(json.dumps(updated.model_dump(), ensure_ascii=False, indent=2))
    return 0


def _cmd_requirement_dismiss(args: argparse.Namespace) -> int:
    with connect(args.db) as connection:
        updated = rr.update_requirement_status(connection, args.id, "dismissed")
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

    competency_parser = subparsers.add_parser("competency", help="Domain Plugin の Competency")
    competency_subparsers = competency_parser.add_subparsers(dest="competency_command", required=True)

    register = competency_subparsers.add_parser("register", help="Domain Plugin の Competency を Goal に登録する")
    register.add_argument("--goal", required=True)
    register.add_argument("--domain", required=True, choices=tuple(DOMAIN_PLUGINS))
    register.add_argument("--english-db", type=Path, default=None, dest="english_db")
    register.add_argument(
        "--domain-db", type=Path, default=None, dest="domain_db",
        help="toeic以外のDomain Plugin用DBパス（既定はplugin側のデフォルト）",
    )
    register.set_defaults(func=_cmd_competency_register)

    competency_list = competency_subparsers.add_parser("list", help="Goal に登録された Competency 一覧")
    competency_list.add_argument("--goal", required=True)
    competency_list.set_defaults(func=_cmd_competency_list)

    mastery = competency_subparsers.add_parser(
        "mastery", help="acenglish の Evidence/Mastery を読んで要約する（Core には保存しない）"
    )
    mastery.add_argument("--goal", required=True)
    mastery.add_argument("--english-db", type=Path, default=None, dest="english_db")
    mastery.add_argument(
        "--domain-db", type=Path, default=None, dest="domain_db",
        help="toeic以外のDomain Plugin用DBパス（既定はplugin側のデフォルト）",
    )
    mastery.add_argument(
        "--open-requirements", action="store_true",
        help="不足が見つかった Competency を resource_requirement として起票する",
    )
    mastery.set_defaults(func=_cmd_competency_mastery)

    resource_parser = subparsers.add_parser("resource", help="教材台帳")
    resource_subparsers = resource_parser.add_subparsers(dest="resource_command", required=True)

    resource_register = resource_subparsers.add_parser("register", help="教材を台帳に登録する")
    resource_register.add_argument("--goal", required=True)
    resource_register.add_argument("--id", required=True, dest="id")
    resource_register.add_argument("--title", required=True)
    resource_register.add_argument("--kind", required=True, help="例: book/pdf/generated/app")
    resource_register.add_argument("--location", help="Drive file_id 等")
    resource_register.add_argument("--authority")
    resource_register.set_defaults(func=_cmd_resource_register)

    resource_list = resource_subparsers.add_parser("list", help="教材一覧")
    resource_list.add_argument("--goal", required=True)
    resource_list.add_argument("--status", choices=("candidate", "reviewed", "active", "deprecated", "archived"))
    resource_list.set_defaults(func=_cmd_resource_list)

    resource_update_status = resource_subparsers.add_parser("update-status", help="教材の状態を変える")
    resource_update_status.add_argument("id")
    resource_update_status.add_argument(
        "status", choices=("candidate", "reviewed", "active", "deprecated", "archived")
    )
    resource_update_status.set_defaults(func=_cmd_resource_update_status)

    requirement_parser = subparsers.add_parser("requirement", help="教材不足の診断")
    requirement_subparsers = requirement_parser.add_subparsers(dest="requirement_command", required=True)

    requirement_list = requirement_subparsers.add_parser("list", help="不足診断の一覧")
    requirement_list.add_argument("--goal", required=True)
    requirement_list.add_argument("--status", choices=("unresolved", "resolved", "dismissed"))
    requirement_list.set_defaults(func=_cmd_requirement_list)

    requirement_resolve = requirement_subparsers.add_parser("resolve", help="不足診断を解消済みにする")
    requirement_resolve.add_argument("id")
    requirement_resolve.set_defaults(func=_cmd_requirement_resolve)

    requirement_dismiss = requirement_subparsers.add_parser("dismiss", help="不足診断を却下する")
    requirement_dismiss.add_argument("id")
    requirement_dismiss.set_defaults(func=_cmd_requirement_dismiss)

    args = parser.parse_args()
    try:
        return args.func(args)
    except (
        goal.GoalNotFoundError,
        goal.DuplicateGoalError,
        goal.InvalidGoalStatusError,
        resource.ResourceNotFoundError,
        resource.DuplicateResourceError,
        resource.InvalidResourceStatusError,
        rr.ResourceRequirementNotFoundError,
        rr.DuplicateResourceRequirementError,
        rr.InvalidResourceRequirementError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
