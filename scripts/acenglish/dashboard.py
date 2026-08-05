"""学習ダッシュボードの集計。

新しい記録の仕組みは増やさない。`skill_state` / `attempt` / `review_queue` /
`revision_candidate` という既存テーブルを読むだけで、進捗・今日のタスク・誤答傾向・
TOEICスコア目安のすべてが出せる（詳細は academic-infra 側の設計メモ参照）。

TOEICスコア推定だけは新規ロジック。公式の採点アルゴリズムは非公開なので、
vocab/grammar/reading の mastery 平均から Reading セクション相当(5-495, 5点刻み)を
出す単純な目安に留め、UIでも「非公式の目安」と明記する前提で設計する。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from . import promote

TREND_DAYS = 14
_TOEIC_MIN, _TOEIC_MAX = 5, 495
_TOEIC_STEP = 5
# generated_item には domain 列が無く kind (vocab/reading/grammar) しか持たない。
# domain は items.py の各 Item サブクラスで kind と1:1に固定されているので変換して揃える。
_KIND_TO_DOMAIN = {"vocab": "vocabulary", "reading": "reading", "grammar": "grammar"}


def _mastery_by_domain(connection: sqlite3.Connection, course_id: str) -> list[dict]:
    rows = connection.execute(
        """
        SELECT ss.domain AS domain, AVG(ss.mastery) AS mastery, SUM(ss.attempts) AS attempts
        FROM skill_state ss
        JOIN material m ON m.review_id = ss.target_ref
        WHERE m.course_id = ?
        GROUP BY ss.domain
        ORDER BY ss.domain
        """,
        (course_id,),
    ).fetchall()
    return [
        {"domain": row["domain"], "mastery": round(row["mastery"], 4), "attempts": row["attempts"]}
        for row in rows
    ]


def _weakest_domain(mastery_by_domain: list[dict]) -> str | None:
    practiced = [row for row in mastery_by_domain if row["attempts"]]
    if not practiced:
        return None
    return min(practiced, key=lambda row: row["mastery"])["domain"]


def _due_counts(connection: sqlite3.Connection, course_id: str, now: str) -> list[dict]:
    rows = connection.execute(
        """
        SELECT gi.kind AS kind, COUNT(*) AS due
        FROM generated_item gi
        LEFT JOIN review_queue rq ON rq.item_id = gi.id
        WHERE gi.course_id = ? AND gi.retired_at IS NULL
          AND (rq.next_review IS NULL OR rq.next_review <= ?)
        GROUP BY gi.kind
        ORDER BY gi.kind
        """,
        (course_id, now),
    ).fetchall()
    return [
        {"domain": _KIND_TO_DOMAIN.get(row["kind"], row["kind"]), "due": row["due"]} for row in rows
    ]


def _trend(connection: sqlite3.Connection, course_id: str, today: datetime) -> list[dict]:
    start = (today - timedelta(days=TREND_DAYS - 1)).date().isoformat()
    rows = connection.execute(
        """
        SELECT date(a.created_at) AS day, COUNT(*) AS attempts, SUM(a.correct) AS correct
        FROM attempt a
        JOIN generated_item gi ON gi.id = a.item_id
        WHERE gi.course_id = ? AND date(a.created_at) >= ?
        GROUP BY day
        """,
        (course_id, start),
    ).fetchall()
    by_day = {row["day"]: {"attempts": row["attempts"], "correct": row["correct"] or 0} for row in rows}

    trend = []
    for offset in range(TREND_DAYS - 1, -1, -1):
        day = (today - timedelta(days=offset)).date().isoformat()
        counts = by_day.get(day, {"attempts": 0, "correct": 0})
        trend.append({"date": day, "attempts": counts["attempts"], "correct": counts["correct"]})
    return trend


def _streak_days(trend: list[dict]) -> int:
    streak = 0
    for entry in reversed(trend):
        if entry["attempts"] == 0:
            break
        streak += 1
    return streak


def _error_causes(connection: sqlite3.Connection, course_id: str) -> list[dict]:
    rows = connection.execute(
        """
        SELECT a.error_cause AS cause, COUNT(*) AS count
        FROM attempt a
        JOIN generated_item gi ON gi.id = a.item_id
        WHERE gi.course_id = ? AND a.error_cause IS NOT NULL
        GROUP BY a.error_cause
        ORDER BY count DESC
        LIMIT 5
        """,
        (course_id,),
    ).fetchall()
    return [{"cause": row["cause"], "count": row["count"]} for row in rows]


def _toeic_reading_estimate(mastery_by_domain: list[dict]) -> dict | None:
    """vocab/grammar/reading の mastery 平均から Reading セクション相当を出す。

    公式のTOEIC採点アルゴリズムは非公開なので、これは較正されていない目安に過ぎない。
    最低1領域でも実績(attempts>0)が無ければ何も返さない。
    """
    values = [row["mastery"] for row in mastery_by_domain if row["attempts"]]
    if not values:
        return None
    average = sum(values) / len(values)
    raw = _TOEIC_MIN + average * (_TOEIC_MAX - _TOEIC_MIN)
    score = int(round(raw / _TOEIC_STEP) * _TOEIC_STEP)
    score = max(_TOEIC_MIN, min(_TOEIC_MAX, score))
    return {
        "score": score,
        "note": "目安（vocab/grammar/readingのmastery平均から算出。公式スコアではない）",
    }


def build_dashboard(connection: sqlite3.Connection, course_id: str) -> dict:
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat(timespec="seconds")

    mastery_by_domain = _mastery_by_domain(connection, course_id)
    trend = _trend(connection, course_id, now)

    return {
        "course_id": course_id,
        "mastery_by_domain": mastery_by_domain,
        "weakest_domain": _weakest_domain(mastery_by_domain),
        "due_counts": _due_counts(connection, course_id, now_iso),
        "trend": trend,
        "streak_days": _streak_days(trend),
        "error_causes": _error_causes(connection, course_id),
        "open_candidates": len(promote.open_candidates(connection, course_id)),
        "toeic_reading_estimate": (
            _toeic_reading_estimate(mastery_by_domain) if course_id == "english" else None
        ),
    }
