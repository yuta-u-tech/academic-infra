"""不足診断: `resource_requirement` テーブルへの CRUD。

`competency.py` / Domain Plugin の `resource_gap_hint()` が返す「何がどう足りないか」を、
Goal に紐付いた不足レコードとして起票する。ここで作るのは「提案のみ」層
（設計書 §5 の `tier='suggest'`）に相当する記録で、承認・自動適用はしない。
"""

from __future__ import annotations

import json
import sqlite3

from .db import now_iso
from .goal import get_goal
from .models import (
    RESOURCE_REQUIREMENT_GAP_KINDS,
    RESOURCE_REQUIREMENT_PRIORITIES,
    RESOURCE_REQUIREMENT_STATUSES,
    ResourceRequirement,
)
from .plugins.base import ResourceGapHint


class ResourceRequirementNotFoundError(Exception):
    pass


class DuplicateResourceRequirementError(Exception):
    pass


class InvalidResourceRequirementError(Exception):
    pass


def _row_to_requirement(row: sqlite3.Row) -> ResourceRequirement:
    data = {key: row[key] for key in row.keys()}
    data["competency_ids"] = json.loads(data["competency_ids"])
    return ResourceRequirement(**data)


def open_requirement(
    connection: sqlite3.Connection,
    goal_id: str,
    requirement_id: str,
    *,
    competency_ids: list[str],
    gap_kind: str,
    priority: str,
    spec: dict,
) -> ResourceRequirement:
    get_goal(connection, goal_id)  # 存在確認
    if gap_kind not in RESOURCE_REQUIREMENT_GAP_KINDS:
        raise InvalidResourceRequirementError(
            f"gap_kind={gap_kind!r} は未知の値です（{', '.join(RESOURCE_REQUIREMENT_GAP_KINDS)} のいずれか）"
        )
    if priority not in RESOURCE_REQUIREMENT_PRIORITIES:
        raise InvalidResourceRequirementError(
            f"priority={priority!r} は未知の値です（{', '.join(RESOURCE_REQUIREMENT_PRIORITIES)} のいずれか）"
        )
    if get_requirement(connection, requirement_id, required=False) is not None:
        raise DuplicateResourceRequirementError(f"requirement_id={requirement_id!r} は既に存在します")

    connection.execute(
        "INSERT INTO resource_requirement (requirement_id, goal_id, competency_ids, gap_kind,"
        " priority, status, spec, created_at) VALUES (?, ?, ?, ?, ?, 'unresolved', ?, ?)",
        (
            requirement_id,
            goal_id,
            json.dumps(competency_ids, ensure_ascii=False),
            gap_kind,
            priority,
            json.dumps(spec, ensure_ascii=False),
            now_iso(),
        ),
    )
    connection.commit()
    return get_requirement(connection, requirement_id)


def open_requirement_from_gap_hint(
    connection: sqlite3.Connection,
    goal_id: str,
    requirement_id: str,
    hint: ResourceGapHint,
    *,
    priority: str = "medium",
) -> ResourceRequirement:
    """Domain Plugin の `resource_gap_hint()` をそのまま起票用の spec に写す。"""
    return open_requirement(
        connection,
        goal_id,
        requirement_id,
        competency_ids=[hint.competency_id],
        gap_kind=hint.gap_kind,
        priority=priority,
        spec={"reason": hint.reason, "source": "domain_plugin"},
    )


def get_requirement(
    connection: sqlite3.Connection, requirement_id: str, *, required: bool = True
) -> ResourceRequirement | None:
    row = connection.execute(
        "SELECT * FROM resource_requirement WHERE requirement_id = ?", (requirement_id,)
    ).fetchone()
    if row is None:
        if required:
            raise ResourceRequirementNotFoundError(f"requirement_id={requirement_id!r} が見つかりません")
        return None
    return _row_to_requirement(row)


def list_requirements(
    connection: sqlite3.Connection, goal_id: str, *, status: str | None = None
) -> list[ResourceRequirement]:
    if status is None:
        rows = connection.execute(
            "SELECT * FROM resource_requirement WHERE goal_id = ? ORDER BY requirement_id",
            (goal_id,),
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT * FROM resource_requirement WHERE goal_id = ? AND status = ?"
            " ORDER BY requirement_id",
            (goal_id, status),
        ).fetchall()
    return [_row_to_requirement(row) for row in rows]


def update_requirement_status(
    connection: sqlite3.Connection, requirement_id: str, status: str
) -> ResourceRequirement:
    if status not in RESOURCE_REQUIREMENT_STATUSES:
        raise InvalidResourceRequirementError(
            f"status={status!r} は未知の値です（{', '.join(RESOURCE_REQUIREMENT_STATUSES)} のいずれか）"
        )
    get_requirement(connection, requirement_id)  # 存在確認
    connection.execute(
        "UPDATE resource_requirement SET status = ? WHERE requirement_id = ?",
        (status, requirement_id),
    )
    connection.commit()
    return get_requirement(connection, requirement_id)
