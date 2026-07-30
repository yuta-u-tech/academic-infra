"""誤答の原因分類と、「資料の不足」への昇格判定。

誤答を履歴として貯めるだけでは資料は良くならない。要件の核心は
「本人の理解不足か、資料の説明不足か」を分けることで、分岐したあとの行き先が違う:

    knowledge_gap   本人の理解不足        → 復習問題を追加する。資料は触らない
    material_gap    資料の説明不足        → revision_candidate を立てる（資料改善へ）
    production_gap  認識できるが産出できない → 産出型の演習を追加する
    vocabulary_gap  語彙不足              → 語彙カードを追加する
    parsing_gap     構文の読み取り不足      → 構文分解の演習を追加する
    speed_gap       処理速度不足           → 時間制限つきで再出題する

material_gap だけが資料更新へ進む。1回の誤答で資料のせいにしないため、
同じ箇所で繰り返し間違えて初めて昇格する（`MATERIAL_GAP_THRESHOLD`）。
"""

from __future__ import annotations

import json
import sqlite3
from enum import Enum

from .db import now_iso
from .model import AttemptSignals, latency_budget_ms

# 同一箇所で何回続けて間違えたら「資料が悪いのでは」と疑い始めるか。
MATERIAL_GAP_THRESHOLD = 3
# 正答でも、想定時間のこの倍数を超えたら処理速度の問題として扱う。
SPEED_GAP_FACTOR = 2.0
# 「認識はできている」と見なす mastery の下限。
RECOGNITION_MASTERY_FLOOR = 0.7


class ErrorCause(str, Enum):
    KNOWLEDGE_GAP = "knowledge_gap"
    MATERIAL_GAP = "material_gap"
    PRODUCTION_GAP = "production_gap"
    VOCABULARY_GAP = "vocabulary_gap"
    PARSING_GAP = "parsing_gap"
    SPEED_GAP = "speed_gap"


def classify(
    connection: sqlite3.Connection,
    signals: AttemptSignals,
    override: str | None = None,
) -> ErrorCause | None:
    """原因を判定する。正答かつ十分速ければ None（原因なし）。

    `override` は Claude や UI からの明示指定。既存の findings.json と同じ思想で、
    意味を読む判断は Claude が担えるようにしてあり、ここは規則で決まる分だけを埋める。
    """
    if override:
        return ErrorCause(override)

    budget = latency_budget_ms(signals.domain)
    if signals.correct:
        return ErrorCause.SPEED_GAP if signals.elapsed_ms > budget * SPEED_GAP_FACTOR else None

    if signals.domain == "reading" and signals.sub_skill == "syntax_parsing":
        return ErrorCause.PARSING_GAP
    if signals.domain == "reading" and signals.sub_skill == "vocabulary":
        return ErrorCause.VOCABULARY_GAP
    if signals.domain == "vocabulary":
        if signals.sub_skill == "recognition":
            return ErrorCause.VOCABULARY_GAP
        # 見て分かる（recognition が育っている）のに書けない＝産出の問題。
        if _mastery(connection, signals.domain, "recognition", signals.target_ref) >= RECOGNITION_MASTERY_FLOOR:
            return ErrorCause.PRODUCTION_GAP

    return ErrorCause.KNOWLEDGE_GAP


def escalate(
    connection: sqlite3.Connection,
    review_id: str,
    domain: str,
    sub_skill: str,
    threshold: int = MATERIAL_GAP_THRESHOLD,
) -> bool:
    """同じ箇所での誤答が閾値に達し、資料側の不足を疑うべきかを返す。

    「本人が覚えていないだけ」(knowledge_gap) の反復だけを昇格対象にする。
    語彙不足や速度不足の反復は資料の書き方の問題ではないので昇格させない。
    """
    row = connection.execute(
        "SELECT error_streak FROM skill_state WHERE domain = ? AND sub_skill = ? AND target_ref = ?",
        (domain, sub_skill, review_id),
    ).fetchone()
    if not row or row["error_streak"] < threshold:
        return False

    recent = connection.execute(
        """
        SELECT error_cause FROM attempt
        WHERE review_id = ? AND domain = ? AND sub_skill = ? AND correct = 0
        ORDER BY id DESC LIMIT ?
        """,
        (review_id, domain, sub_skill, threshold),
    ).fetchall()
    causes = [r["error_cause"] for r in recent]
    if len(causes) < threshold:
        return False
    return all(cause == ErrorCause.KNOWLEDGE_GAP.value for cause in causes)


def open_revision_candidate(
    connection: sqlite3.Connection,
    review_id: str,
    course_id: str,
    source_file: str,
    title: str,
    problem: str,
    fix_spec: list[str],
    evidence: dict,
    target_kind: str = "course_repo",
) -> int:
    """資料への追記候補を1件立てる（同一 review_id で open が既にあれば作り直さない）。

    ここはまだ Draft ですらない。ユーザーが確認して初めて、科目資料なら findings.json →
    `promote_drive_comments.py` で Issue に、外部素材なら english-notes の drafts/ になる。
    """
    existing = connection.execute(
        "SELECT id FROM revision_candidate WHERE review_id = ? AND status = 'open'",
        (review_id,),
    ).fetchone()
    if existing:
        return existing["id"]

    cursor = connection.execute(
        """
        INSERT INTO revision_candidate (
            review_id, course_id, source_file, title, problem, fix_spec, evidence,
            status, target_kind, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
        """,
        (
            review_id,
            course_id,
            source_file,
            title,
            problem,
            json.dumps(fix_spec, ensure_ascii=False),
            json.dumps(evidence, ensure_ascii=False),
            target_kind,
            now_iso(),
        ),
    )
    connection.commit()
    return int(cursor.lastrowid)


def next_action(cause: ErrorCause | None) -> str:
    """原因ごとの次の一手。生成コマンド側がこれを見て何を作るか決める。"""
    return {
        ErrorCause.KNOWLEDGE_GAP: "review_drill",
        ErrorCause.MATERIAL_GAP: "revise_material",
        ErrorCause.PRODUCTION_GAP: "production_drill",
        ErrorCause.VOCABULARY_GAP: "vocab_card",
        ErrorCause.PARSING_GAP: "syntax_drill",
        ErrorCause.SPEED_GAP: "timed_retry",
    }.get(cause, "none")


def _mastery(connection: sqlite3.Connection, domain: str, sub_skill: str, target_ref: str) -> float:
    row = connection.execute(
        "SELECT mastery FROM skill_state WHERE domain = ? AND sub_skill = ? AND target_ref = ?",
        (domain, sub_skill, target_ref),
    ).fetchone()
    return row["mastery"] if row else 0.0
