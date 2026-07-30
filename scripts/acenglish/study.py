"""学習の閉ループ本体。

    出題 → 回答 → 誤答原因の分類 → 学習者モデル更新 → 復習キュー再計算
        → （資料の不足と判定されたら）追記候補を立てる

要件 §14 の一本道はここに集約されている。API も CLI もこの関数を呼ぶだけにして、
経路ごとに挙動がずれないようにする。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .db import now_iso
from .diagnose import ErrorCause, classify, escalate, next_action, open_revision_candidate
from .items import ReadingItem, VocabItem
from .model import AttemptSignals, schedule_review, update_skill_state

_ITEM_TYPES = {"vocab": VocabItem, "reading": ReadingItem}


@dataclass(frozen=True)
class AnswerOutcome:
    """1回の回答の結果。UI にそのまま返せる形。"""

    attempt_id: int
    correct: bool
    quality_domain: str
    error_cause: str | None
    next_action: str
    skill_state: dict
    review: dict
    revision_candidate_id: int | None


def start_session(connection: sqlite3.Connection, course_id: str, note: str | None = None) -> int:
    cursor = connection.execute(
        "INSERT INTO learning_session (course_id, started_at, note) VALUES (?, ?, ?)",
        (course_id, now_iso(), note),
    )
    connection.commit()
    return int(cursor.lastrowid)


def end_session(connection: sqlite3.Connection, session_id: int) -> None:
    connection.execute(
        "UPDATE learning_session SET ended_at = ? WHERE id = ?", (now_iso(), session_id)
    )
    connection.commit()


def load_item(connection: sqlite3.Connection, item_id: int) -> tuple[dict, VocabItem | ReadingItem]:
    row = connection.execute("SELECT * FROM generated_item WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise LookupError(f"generated_item {item_id} がありません。")
    model = _ITEM_TYPES[row["kind"]]
    return dict(row), model.model_validate_json(row["payload"])


def answer(
    connection: sqlite3.Connection,
    session_id: int,
    item_id: int,
    response: str,
    elapsed_ms: int,
    self_confidence: float | None = None,
    hint_used: bool = False,
    retry_count: int = 0,
    cause_override: str | None = None,
) -> AnswerOutcome:
    """回答を1件記録し、閉ループを最後まで回す。"""
    row, item = load_item(connection, item_id)
    correct = item.check(response)

    signals = AttemptSignals(
        domain=item.domain,
        sub_skill=item.sub_skill,
        target_ref=row["review_id"],
        correct=correct,
        elapsed_ms=elapsed_ms,
        hint_used=hint_used,
        retry_count=retry_count,
        self_confidence=self_confidence,
        days_since_last=_days_since_last(connection, item_id),
    )

    cause = classify(connection, signals, cause_override)

    cursor = connection.execute(
        """
        INSERT INTO attempt (
            session_id, item_id, review_id, domain, sub_skill, response, correct,
            elapsed_ms, self_confidence, hint_used, retry_count, error_cause,
            days_since_last, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            item_id,
            row["review_id"],
            item.domain,
            item.sub_skill,
            response,
            1 if correct else 0,
            elapsed_ms,
            self_confidence,
            1 if hint_used else 0,
            retry_count,
            cause.value if cause else None,
            signals.days_since_last,
            now_iso(),
        ),
    )
    attempt_id = int(cursor.lastrowid)
    connection.commit()

    skill_state = update_skill_state(connection, signals)
    review = schedule_review(connection, item_id, row["review_id"], signals)

    candidate_id = None
    if not correct and escalate(connection, row["review_id"], item.domain, item.sub_skill):
        cause = ErrorCause.MATERIAL_GAP
        connection.execute(
            "UPDATE attempt SET error_cause = ? WHERE id = ?", (cause.value, attempt_id)
        )
        connection.commit()
        candidate_id = _open_candidate(connection, row, item, skill_state)

    return AnswerOutcome(
        attempt_id=attempt_id,
        correct=correct,
        quality_domain=item.domain,
        error_cause=cause.value if cause else None,
        next_action=next_action(cause),
        skill_state=skill_state,
        review=review,
        revision_candidate_id=candidate_id,
    )


def _open_candidate(
    connection: sqlite3.Connection,
    row: dict,
    item: VocabItem | ReadingItem,
    skill_state: dict,
) -> int:
    """資料の説明不足として追記候補を立てる。

    問題文・修正仕様は「誤答の事実」から機械的に組み立てられる範囲に留める。
    どう書き直すかの本文は Claude が Issue 化の直前に肉付けする前提
    （既存の findings.json と同じ分担）。
    """
    material = connection.execute(
        "SELECT * FROM material WHERE review_id = ?", (row["review_id"],)
    ).fetchone()
    title = material["title"] if material else row["review_id"]
    source_file = material["source_file"] if material else "(未確定)"

    problem = (
        f"「{title}」について、{item.domain}/{item.sub_skill} の演習で "
        f"{skill_state['error_streak']}回連続して誤答している。"
        f"平均的な回答時間の中央値は {skill_state['latency_ms_p50']}ms、"
        f"ヒント使用率は {skill_state['hint_rate']:.0%}。"
        "本人が覚えていないだけでなく、資料側の説明・例が不足している可能性がある。"
    )
    fix_spec = [
        f"{title} の該当箇所に、誤答が集中している論点の説明を追記する",
        "具体例を1つ以上追加する（既存の記号体系は変えない）",
        "英語で説明する際の対応表現を併記する",
    ]
    evidence = {
        "review_id": row["review_id"],
        "domain": item.domain,
        "sub_skill": item.sub_skill,
        "error_streak": skill_state["error_streak"],
        "mastery": skill_state["mastery"],
        "item_prompt": item.prompt(),
        "source_commit": row["source_commit"],
    }
    return open_revision_candidate(
        connection,
        review_id=row["review_id"],
        course_id=row["course_id"],
        source_file=source_file,
        title=f"{title} の説明が不足している（英語演習での誤答{skill_state['error_streak']}回）",
        problem=problem,
        fix_spec=fix_spec,
        evidence=evidence,
    )


def _days_since_last(connection: sqlite3.Connection, item_id: int) -> float | None:
    row = connection.execute(
        "SELECT created_at FROM attempt WHERE item_id = ? ORDER BY id DESC LIMIT 1", (item_id,)
    ).fetchone()
    if row is None:
        return None
    previous = datetime.fromisoformat(row["created_at"])
    now = datetime.fromisoformat(now_iso())
    return round((now - previous).total_seconds() / 86_400, 4)


def item_for_ui(connection: sqlite3.Connection, item_id: int) -> dict[str, Any]:
    """出題用。答え（answer_index / word）は含めない。"""
    row, item = load_item(connection, item_id)
    payload = json.loads(row["payload"])
    if row["kind"] == "reading":
        payload.pop("answer_index", None)
        payload.pop("explanation", None)
    else:
        payload.pop("word", None)
    return {
        "item_id": item_id,
        "kind": row["kind"],
        "review_id": row["review_id"],
        "course_id": row["course_id"],
        "difficulty": row["difficulty"],
        "domain": item.domain,
        "sub_skill": item.sub_skill,
        "payload": payload,
    }
