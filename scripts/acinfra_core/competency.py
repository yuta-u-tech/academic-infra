"""Competency Engine: Domain Plugin の宣言する Competency を Goal に紐付けて Core へ登録する。

`competency` テーブルへの書き込みはここに一本化する。Domain Plugin 自体は
`goal_id` を知らない（複数 Goal から同じ Plugin を使い回せるようにするため）。
"""

from __future__ import annotations

import sqlite3

from .db import now_iso
from .goal import get_goal
from .models import Competency
from .plugins.base import DomainPlugin


def _row_to_competency(row: sqlite3.Row) -> Competency:
    return Competency(**{key: row[key] for key in row.keys()})


def register_domain_competencies(
    connection: sqlite3.Connection, goal_id: str, plugin: DomainPlugin
) -> list[Competency]:
    """`plugin.competencies()` を `goal_id` に紐付けて登録する。既存分はスキップする。"""
    get_goal(connection, goal_id)  # 存在確認
    timestamp = now_iso()
    for template in plugin.competencies():
        existing = connection.execute(
            "SELECT 1 FROM competency WHERE competency_id = ?", (template.competency_id,)
        ).fetchone()
        if existing is not None:
            continue
        connection.execute(
            "INSERT INTO competency (competency_id, goal_id, domain_id, parent_competency_id,"
            " title, domain_ref, exam_weight, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                template.competency_id,
                goal_id,
                template.domain_id,
                template.parent_competency_id,
                template.title,
                template.domain_ref,
                template.exam_weight,
                timestamp,
            ),
        )
    connection.commit()
    return list_competencies(connection, goal_id)


def list_competencies(connection: sqlite3.Connection, goal_id: str) -> list[Competency]:
    rows = connection.execute(
        "SELECT * FROM competency WHERE goal_id = ? ORDER BY competency_id", (goal_id,)
    ).fetchall()
    return [_row_to_competency(row) for row in rows]
