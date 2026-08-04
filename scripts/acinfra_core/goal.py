"""Goal Engine: goal テーブルへの CRUD。

設計書 §9 の Phase 1 完了条件のうち、Core の Goal 層を最初に実装する
（acinfra_core 新設 Issue のスコープ）。Competency/Resource/Research/Proposal/
Intervention はここでは扱わない。
"""

from __future__ import annotations

import sqlite3

from .db import now_iso
from .models import GOAL_STATUSES, Goal


class GoalNotFoundError(Exception):
    pass


class DuplicateGoalError(Exception):
    pass


class InvalidGoalStatusError(Exception):
    pass


def _row_to_goal(row: sqlite3.Row) -> Goal:
    return Goal(**{key: row[key] for key in row.keys()})


def create_goal(
    connection: sqlite3.Connection,
    goal_id: str,
    title: str,
    *,
    parent_goal_id: str | None = None,
    target_value: str | None = None,
    current_value: str | None = None,
    deadline: str | None = None,
    priority: int = 3,
    evaluation_method: str | None = None,
) -> Goal:
    if get_goal(connection, goal_id, required=False) is not None:
        raise DuplicateGoalError(f"goal_id={goal_id!r} は既に存在します")
    if parent_goal_id is not None and get_goal(connection, parent_goal_id, required=False) is None:
        raise GoalNotFoundError(f"parent_goal_id={parent_goal_id!r} が見つかりません")

    timestamp = now_iso()
    connection.execute(
        "INSERT INTO goal (goal_id, parent_goal_id, title, target_value, current_value,"
        " deadline, priority, evaluation_method, status, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)",
        (
            goal_id,
            parent_goal_id,
            title,
            target_value,
            current_value,
            deadline,
            priority,
            evaluation_method,
            timestamp,
            timestamp,
        ),
    )
    connection.commit()
    return get_goal(connection, goal_id)


def get_goal(connection: sqlite3.Connection, goal_id: str, *, required: bool = True) -> Goal | None:
    row = connection.execute("SELECT * FROM goal WHERE goal_id = ?", (goal_id,)).fetchone()
    if row is None:
        if required:
            raise GoalNotFoundError(f"goal_id={goal_id!r} が見つかりません")
        return None
    return _row_to_goal(row)


def list_goals(connection: sqlite3.Connection, *, status: str | None = None) -> list[Goal]:
    if status is None:
        rows = connection.execute("SELECT * FROM goal ORDER BY priority, goal_id").fetchall()
    else:
        rows = connection.execute(
            "SELECT * FROM goal WHERE status = ? ORDER BY priority, goal_id", (status,)
        ).fetchall()
    return [_row_to_goal(row) for row in rows]


def update_goal_status(connection: sqlite3.Connection, goal_id: str, status: str) -> Goal:
    if status not in GOAL_STATUSES:
        raise InvalidGoalStatusError(
            f"status={status!r} は未知の値です（{', '.join(GOAL_STATUSES)} のいずれか）"
        )
    get_goal(connection, goal_id)  # 存在確認（無ければ GoalNotFoundError）
    connection.execute(
        "UPDATE goal SET status = ?, updated_at = ? WHERE goal_id = ?",
        (status, now_iso(), goal_id),
    )
    connection.commit()
    return get_goal(connection, goal_id)
