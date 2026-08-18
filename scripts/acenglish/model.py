"""学習者モデルの更新と復習間隔（SM-2）。

要件の中心は「mastery を単純な正答率で表さない」こと。正答でも、ヒントを使った・
遅かった・自信が無かった・何度もやり直した場合は、身についた度合いは低い。
`response_quality()` がその割引を一手に引き受け、mastery はその品質へ寄っていく。

間隔計算は goigoi (`word.schema.json` v1) と同じ SM-2。interval / ease_factor /
repetitions の3値も同じ意味で持つ。別アルゴリズムを混ぜると goigoi-data と
同期したときに状態が壊れる。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .db import now_iso

# 「速い/遅い」の基準。ドメインごとに要求される処理速度が違う（読解は読む時間が要る）。
LATENCY_BUDGET_MS: dict[str, int] = {
    "vocabulary": 6_000,
    "grammar": 10_000,
    "reading": 45_000,
    "listening": 30_000,
    "writing": 300_000,
    "speaking": 120_000,
}
_DEFAULT_BUDGET_MS = 30_000

_MIN_ALPHA = 0.10
_MAX_ALPHA = 0.50
_SLOW_FLOOR = 0.5  # どれだけ遅くても、正答である以上ここまでしか割り引かない
_CONFIDENCE_SCALE = 5.0  # 試行が何回たまれば推定を信用してよいか


@dataclass(frozen=True)
class AttemptSignals:
    """学習者モデルを動かす根拠。正誤以外の全てがここに乗る。"""

    domain: str
    sub_skill: str
    target_ref: str
    correct: bool
    elapsed_ms: int
    hint_used: bool = False
    retry_count: int = 0
    self_confidence: float | None = None
    days_since_last: float | None = None


def latency_budget_ms(domain: str) -> int:
    return LATENCY_BUDGET_MS.get(domain, _DEFAULT_BUDGET_MS)


def response_quality(signals: AttemptSignals) -> float:
    """0.0–1.0。「どれだけ確かに身についた回答か」。

    誤答は 0。正答は 1.0 から始めて、ヒント・やり直し・遅さ・自信の低さで割り引く。
    「正答だが遅くヒント有り」が「正答で速くヒント無し」と同じ扱いにならないのが要点。
    """
    if not signals.correct:
        return 0.0

    quality = 1.0
    if signals.hint_used:
        quality *= 0.5
    if signals.retry_count > 0:
        quality *= 1.0 / (1.0 + signals.retry_count)

    budget = latency_budget_ms(signals.domain)
    if signals.elapsed_ms > budget:
        quality *= max(_SLOW_FLOOR, budget / signals.elapsed_ms)

    if signals.self_confidence is not None:
        # 自信0でも正答は正答なので、0.6を下限にして完全には潰さない。
        quality *= 0.6 + 0.4 * max(0.0, min(1.0, signals.self_confidence))

    return round(quality, 4)


def learning_rate(attempts: int) -> float:
    """試行が少ないうちは大きく動かし、たまってきたら慎重にする。"""
    return max(_MIN_ALPHA, min(_MAX_ALPHA, 1.0 / (attempts + 2)))


def next_mastery(current: float, quality: float, attempts: int) -> float:
    return round(current + learning_rate(attempts) * (quality - current), 4)


def quality_to_grade(quality: float, correct: bool) -> int:
    """SM-2 の 0–5 グレードへ。誤答は必ず 3 未満（= 間隔リセット）にする。"""
    if not correct:
        return 2 if quality > 0 else 0
    return max(3, min(5, round(2 + quality * 3)))


def sm2(interval: int, ease_factor: float, repetitions: int, grade: int) -> tuple[int, float, int]:
    """SM-2 の次回間隔。goigoi と同じ実装でなければならない。"""
    if grade >= 3:
        if repetitions == 0:
            interval = 1
        elif repetitions == 1:
            interval = 6
        else:
            interval = max(1, round(interval * ease_factor))
        repetitions += 1
    else:
        interval = 1
        repetitions = 0

    ease_factor += 0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02)
    ease_factor = max(1.3, min(5.0, ease_factor))
    return interval, round(ease_factor, 4), repetitions


def update_skill_state(connection: sqlite3.Connection, signals: AttemptSignals) -> dict:
    """1回の回答で skill_state を進める。更新後の行を dict で返す。"""
    key = (signals.domain, signals.sub_skill, signals.target_ref)
    row = connection.execute(
        "SELECT * FROM skill_state WHERE domain = ? AND sub_skill = ? AND target_ref = ?",
        key,
    ).fetchone()

    attempts = row["attempts"] if row else 0
    mastery = row["mastery"] if row else 0.0
    hint_rate = row["hint_rate"] if row else 0.0
    error_streak = row["error_streak"] if row else 0
    retention_days = row["retention_days"] if row else None

    quality = response_quality(signals)
    new_attempts = attempts + 1
    new_mastery = next_mastery(mastery, quality, attempts)
    new_hint_rate = round((hint_rate * attempts + (1 if signals.hint_used else 0)) / new_attempts, 4)
    new_error_streak = 0 if signals.correct else error_streak + 1
    if signals.correct and signals.days_since_last is not None:
        # 「時間が空いても思い出せた」最長期間。保持の指標なので最大値を採る。
        retention_days = max(retention_days or 0.0, signals.days_since_last)

    latency_p50 = _median_latency(connection, key)

    connection.execute(
        """
        INSERT INTO skill_state (
            domain, sub_skill, target_ref, mastery, confidence, latency_ms_p50,
            hint_rate, retention_days, error_streak, attempts, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (domain, sub_skill, target_ref) DO UPDATE SET
            mastery = excluded.mastery,
            confidence = excluded.confidence,
            latency_ms_p50 = excluded.latency_ms_p50,
            hint_rate = excluded.hint_rate,
            retention_days = excluded.retention_days,
            error_streak = excluded.error_streak,
            attempts = excluded.attempts,
            updated_at = excluded.updated_at
        """,
        (
            *key,
            new_mastery,
            round(new_attempts / (new_attempts + _CONFIDENCE_SCALE), 4),
            latency_p50,
            new_hint_rate,
            retention_days,
            new_error_streak,
            new_attempts,
            now_iso(),
        ),
    )
    connection.commit()

    updated = connection.execute(
        "SELECT * FROM skill_state WHERE domain = ? AND sub_skill = ? AND target_ref = ?",
        key,
    ).fetchone()
    return dict(updated)


def _median_latency(connection: sqlite3.Connection, key: tuple[str, str, str]) -> int | None:
    """記録済み回答から実測の中央値を取る（EWMA で近似しない）。"""
    domain, sub_skill, target_ref = key
    rows = connection.execute(
        """
        SELECT elapsed_ms FROM attempt
        WHERE domain = ? AND sub_skill = ? AND review_id = ?
        ORDER BY elapsed_ms
        """,
        (domain, sub_skill, target_ref),
    ).fetchall()
    if not rows:
        return None
    values = [r["elapsed_ms"] for r in rows]
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return (values[middle - 1] + values[middle]) // 2


def schedule_review(
    connection: sqlite3.Connection, item_id: int, review_id: str, signals: AttemptSignals
) -> dict:
    """復習キューを SM-2 で進める。"""
    row = connection.execute(
        "SELECT * FROM review_queue WHERE item_id = ?", (item_id,)
    ).fetchone()
    interval = row["interval"] if row else 0
    ease_factor = row["ease_factor"] if row else 2.5
    repetitions = row["repetitions"] if row else 0

    grade = quality_to_grade(response_quality(signals), signals.correct)
    interval, ease_factor, repetitions = sm2(interval, ease_factor, repetitions, grade)

    now = datetime.now(timezone.utc)
    next_review = (now + timedelta(days=interval)).isoformat(timespec="seconds")

    connection.execute(
        """
        INSERT INTO review_queue (
            item_id, review_id, interval, ease_factor, repetitions, next_review, last_reviewed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (item_id) DO UPDATE SET
            interval = excluded.interval,
            ease_factor = excluded.ease_factor,
            repetitions = excluded.repetitions,
            next_review = excluded.next_review,
            last_reviewed_at = excluded.last_reviewed_at
        """,
        (
            item_id,
            review_id,
            interval,
            ease_factor,
            repetitions,
            next_review,
            now.isoformat(timespec="seconds"),
        ),
    )
    connection.commit()
    return dict(connection.execute("SELECT * FROM review_queue WHERE item_id = ?", (item_id,)).fetchone())


def due_items(
    connection: sqlite3.Connection,
    course_id: str | None = None,
    limit: int = 20,
    kinds: list[str] | None = None,
    mix: bool = True,
) -> list[dict]:
    """今日出す問題を選ぶ。

    順序は **期限が来た復習が先、未出題は後**。逆にすると、2,000語規模のデッキでは
    未出題が尽きるまで復習が一度も回ってこず、間隔反復が成立しない
    （出題されない復習は、忘れたことにすら気づけない）。

    `mix=True` のときは種別を round-robin で混ぜる。ID 順のままだと語彙2,282件の後ろに
    読解・文法が並び、実際には永久に到達しない。
    """
    query = """
        SELECT gi.*, rq.next_review, rq.interval, rq.repetitions
        FROM generated_item AS gi
        LEFT JOIN review_queue AS rq ON rq.item_id = gi.id
        WHERE gi.retired_at IS NULL
          AND (rq.next_review IS NULL OR rq.next_review <= ?)
        {course_filter}
        {kind_filter}
        ORDER BY (rq.next_review IS NULL), rq.next_review, gi.id
        LIMIT ?
    """
    def run(kind_filter: str, extra: list, row_limit: int) -> list[dict]:
        parameters: list = [now_iso()]
        course_filter = ""
        if course_id:
            course_filter = "AND gi.course_id = ?"
            parameters.append(course_id)
        parameters.extend(extra)
        parameters.append(row_limit)
        sql = query.format(course_filter=course_filter, kind_filter=kind_filter)
        return [dict(row) for row in connection.execute(sql, parameters).fetchall()]

    if not mix:
        placeholders = f"AND gi.kind IN ({','.join('?' for _ in kinds)})" if kinds else ""
        return run(placeholders, list(kinds or []), limit)

    # 種別ごとに別々に引く。1本のクエリから間引く方式では、語彙が数千件あると
    # 上位が全部語彙で埋まり、読解・文法が母数にすら入らない。
    available = kinds or _available_kinds(connection, course_id)
    per_kind: dict[str, list[dict]] = {}
    for kind in available:
        if kind != "vocab":
            per_kind[kind] = run("AND gi.kind = ?", [kind], limit)
            continue
        # 語彙は recall / recognition も交互にする。kind だけで混ぜると、古い
        # recall 行が数千件並んだ後に追加した recognition へ到達できない。
        sub_skills = [
            row["sub_skill"]
            for row in connection.execute(
                """SELECT DISTINCT COALESCE(json_extract(payload, '$.sub_skill'), 'recall')
                          AS sub_skill
                   FROM generated_item
                   WHERE kind = 'vocab' AND retired_at IS NULL
                     AND (? IS NULL OR course_id = ?)
                   ORDER BY sub_skill""",
                (course_id, course_id),
            )
        ]
        per_sub_skill = {
            sub_skill: run(
                "AND gi.kind = ? AND COALESCE(json_extract(gi.payload, '$.sub_skill'), 'recall') = ?",
                [kind, sub_skill], limit,
            )
            for sub_skill in sub_skills
        }
        per_kind[kind] = _interleave(per_sub_skill, limit)
    return _interleave(per_kind, limit)


def _available_kinds(connection: sqlite3.Connection, course_id: str | None) -> list[str]:
    sql = "SELECT DISTINCT kind FROM generated_item WHERE retired_at IS NULL"
    parameters: tuple = ()
    if course_id:
        sql += " AND course_id = ?"
        parameters = (course_id,)
    return [row["kind"] for row in connection.execute(sql + " ORDER BY kind", parameters)]


def _interleave(per_kind: dict[str, list[dict]], limit: int) -> list[dict]:
    """種別を1件ずつ順番に取り出す。尽きた種別は飛ばして残りで埋める。"""
    selected: list[dict] = []
    while len(selected) < limit and any(per_kind.values()):
        for queue in per_kind.values():
            if not queue:
                continue
            selected.append(queue.pop(0))
            if len(selected) == limit:
                break
    return selected
