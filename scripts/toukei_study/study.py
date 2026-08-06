"""問題の取り込み・出題・採点・習熟度更新。"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from .db import now_iso

_MASTERY_ALPHA = 0.3  # 直近の正誤を強めに反映する（10日しかないため古い実績を引きずらない）
_CONFIDENCE_SATURATION_ATTEMPTS = 10


@dataclass
class Problem:
    id: int
    competency_id: str
    question: str
    choices: list[str]
    answer_index: int
    explanation: str


def ingest_problems(connection: sqlite3.Connection, set_id: str, competency_id: str, items: list[dict]) -> int:
    now = now_iso()
    inserted = 0
    for item in items:
        connection.execute(
            "INSERT INTO problem (competency_id, question, choices, answer_index, explanation, set_id, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                competency_id,
                item["question"],
                json.dumps(item["choices"], ensure_ascii=False),
                item["answer_index"],
                item["explanation"],
                set_id,
                now,
            ),
        )
        inserted += 1
    connection.commit()
    return inserted


def next_batch(connection: sqlite3.Connection, competency_id: str | None, count: int) -> list[Problem]:
    """未回答を優先し、無ければ誤答が多かった問題を優先して出す。"""
    where = "WHERE p.competency_id = ?" if competency_id else ""
    params: tuple = (competency_id,) if competency_id else ()
    rows = connection.execute(
        f"""
        SELECT p.id, p.competency_id, p.question, p.choices, p.answer_index, p.explanation,
               COUNT(a.id) AS attempts,
               COALESCE(SUM(1 - a.correct), 0) AS misses
        FROM problem p
        LEFT JOIN attempt a ON a.problem_id = p.id
        {where}
        GROUP BY p.id
        ORDER BY (attempts > 0) ASC, misses DESC, attempts ASC, RANDOM()
        LIMIT ?
        """,
        (*params, count),
    ).fetchall()
    return [
        Problem(
            id=row["id"],
            competency_id=row["competency_id"],
            question=row["question"],
            choices=json.loads(row["choices"]),
            answer_index=row["answer_index"],
            explanation=row["explanation"],
        )
        for row in rows
    ]


def record_attempt(connection: sqlite3.Connection, problem: Problem, chosen_index: int) -> bool:
    correct = chosen_index == problem.answer_index
    now = now_iso()
    connection.execute(
        "INSERT INTO attempt (problem_id, competency_id, chosen_index, correct, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (problem.id, problem.competency_id, chosen_index, int(correct), now),
    )
    _update_skill_state(connection, problem.competency_id, correct)
    connection.commit()
    return correct


def _update_skill_state(connection: sqlite3.Connection, competency_id: str, correct: bool) -> None:
    row = connection.execute(
        "SELECT mastery, confidence, attempts, error_streak FROM skill_state WHERE competency_id = ?",
        (competency_id,),
    ).fetchone()
    if row is None:
        mastery, attempts, error_streak = 0.5, 0, 0
    else:
        mastery, attempts, error_streak = row["mastery"], row["attempts"], row["error_streak"]

    target = 1.0 if correct else 0.0
    new_mastery = mastery + _MASTERY_ALPHA * (target - mastery)
    new_attempts = attempts + 1
    new_error_streak = 0 if correct else error_streak + 1
    new_confidence = min(1.0, new_attempts / _CONFIDENCE_SATURATION_ATTEMPTS)

    connection.execute(
        """
        INSERT INTO skill_state (competency_id, mastery, confidence, attempts, error_streak, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(competency_id) DO UPDATE SET
            mastery = excluded.mastery,
            confidence = excluded.confidence,
            attempts = excluded.attempts,
            error_streak = excluded.error_streak,
            updated_at = excluded.updated_at
        """,
        (competency_id, round(new_mastery, 4), round(new_confidence, 4), new_attempts, new_error_streak, now_iso()),
    )


def status(connection: sqlite3.Connection) -> list[dict]:
    rows = connection.execute(
        "SELECT competency_id, mastery, confidence, attempts, error_streak, updated_at FROM skill_state"
        " ORDER BY mastery ASC"
    ).fetchall()
    return [dict(row) for row in rows]
