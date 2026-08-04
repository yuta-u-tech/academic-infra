"""Resource Registry: 教材の台帳（`resource` テーブル）への CRUD。

設計書 §7 の8番目「教材Registryと不足診断」のうち、台帳側の実装。
不足の検出・提案は `resource_requirement.py` が担当する。
"""

from __future__ import annotations

import sqlite3

from .db import now_iso
from .goal import get_goal
from .models import RESOURCE_STATUSES, Resource


class ResourceNotFoundError(Exception):
    pass


class DuplicateResourceError(Exception):
    pass


class InvalidResourceStatusError(Exception):
    pass


def _row_to_resource(row: sqlite3.Row) -> Resource:
    return Resource(**{key: row[key] for key in row.keys()})


def register_resource(
    connection: sqlite3.Connection,
    goal_id: str,
    resource_id: str,
    title: str,
    kind: str,
    *,
    location: str | None = None,
    status: str = "candidate",
    authority: str | None = None,
) -> Resource:
    get_goal(connection, goal_id)  # 存在確認
    if status not in RESOURCE_STATUSES:
        raise InvalidResourceStatusError(
            f"status={status!r} は未知の値です（{', '.join(RESOURCE_STATUSES)} のいずれか）"
        )
    if get_resource(connection, resource_id, required=False) is not None:
        raise DuplicateResourceError(f"resource_id={resource_id!r} は既に存在します")

    timestamp = now_iso()
    connection.execute(
        "INSERT INTO resource (resource_id, goal_id, title, kind, location, status,"
        " authority, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (resource_id, goal_id, title, kind, location, status, authority, timestamp, timestamp),
    )
    connection.commit()
    return get_resource(connection, resource_id)


def get_resource(
    connection: sqlite3.Connection, resource_id: str, *, required: bool = True
) -> Resource | None:
    row = connection.execute("SELECT * FROM resource WHERE resource_id = ?", (resource_id,)).fetchone()
    if row is None:
        if required:
            raise ResourceNotFoundError(f"resource_id={resource_id!r} が見つかりません")
        return None
    return _row_to_resource(row)


def list_resources(
    connection: sqlite3.Connection, goal_id: str, *, status: str | None = None
) -> list[Resource]:
    if status is None:
        rows = connection.execute(
            "SELECT * FROM resource WHERE goal_id = ? ORDER BY resource_id", (goal_id,)
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT * FROM resource WHERE goal_id = ? AND status = ? ORDER BY resource_id",
            (goal_id, status),
        ).fetchall()
    return [_row_to_resource(row) for row in rows]


def update_resource_status(connection: sqlite3.Connection, resource_id: str, status: str) -> Resource:
    if status not in RESOURCE_STATUSES:
        raise InvalidResourceStatusError(
            f"status={status!r} は未知の値です（{', '.join(RESOURCE_STATUSES)} のいずれか）"
        )
    get_resource(connection, resource_id)  # 存在確認
    connection.execute(
        "UPDATE resource SET status = ?, updated_at = ? WHERE resource_id = ?",
        (status, now_iso(), resource_id),
    )
    connection.commit()
    return get_resource(connection, resource_id)
