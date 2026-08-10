"""毎日の単語テスト（語彙MCQ）用の出題ローテーション。

TOEIC語彙（`fetch-toeic` で取り込み済みの2,282語）は既に語義・例文を持っているため、
Part5/Part7と違い**生成は不要**。単語プールからの抽出・選択肢の組み立てだけで完結する
（決定論的コード。Claudeが文面を作る必要はない）。

「毎日ランダムに出すが、1サイクル（プール全体を1周し終える）までは同じ語を出さない」
という要件のため、単純な random.sample を毎回呼ぶのではなく、
シャッフルした順序と読み進めた位置（cursor）を状態として永続化する。
1周し終えたら再シャッフルして次のサイクルに入る。

**苦手語の再出題（2026-08-10追加）**: Forms解答提出（`toeic_forms_cli.py record`）で
`attempt`テーブルに正誤が残るようになったため、直近の誤答語を次回のバッチへ優先的に
混ぜる。Part5の`weak-points`と違い、語彙は「同じ語をどのpatternで出すか」のような
文脈判断が要らない（単語と意味の組は固定）ので、判断をClaudeに委ねず
`weak_review_ids()`で完全に決定論的に選ぶ。「その語の直近の回答が不正解」だった
ものだけを対象にする（過去に一度でも間違えた語を無条件に出し続けると、既に
克服した語がいつまでも残ってしまうため）。
"""

from __future__ import annotations

import json
import random
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .db import default_home

STATE_FILENAME = "vocab-quiz-state.json"


@dataclass(frozen=True)
class VocabEntry:
    review_id: str
    word: str
    meaning: str
    example: str


def load_pool(connection: sqlite3.Connection) -> list[VocabEntry]:
    """TOEIC語彙プールを読む（VOA/TED経由で取り込まれた雑多な語彙は対象外）。"""
    rows = connection.execute(
        "SELECT review_id, payload FROM generated_item "
        "WHERE kind = 'vocab' AND review_id LIKE 'toeic.%' AND retired_at IS NULL "
        "ORDER BY review_id"
    ).fetchall()
    pool = []
    for row in rows:
        payload = json.loads(row["payload"])
        pool.append(VocabEntry(
            review_id=row["review_id"],
            word=payload["word"],
            meaning=payload["meaning"],
            example=payload.get("example") or "",
        ))
    return pool


def _state_path(home: Path | None = None) -> Path:
    return (home or default_home()) / STATE_FILENAME


def _fresh_shuffle(pool_ids: list[str], cycle: int) -> dict:
    order = list(pool_ids)
    random.shuffle(order)
    return {"order": order, "cursor": 0, "cycle": cycle}


def _load_state(pool_ids: list[str], path: Path) -> dict:
    if path.exists():
        state = json.loads(path.read_text(encoding="utf-8"))
        # プールの語数が変わっていなければ、進行中のシャッフル順をそのまま使う。
        # 変わっていたら（追加・削除があった）安全側で作り直す。
        if set(state.get("order", [])) == set(pool_ids):
            return state
    return _fresh_shuffle(pool_ids, cycle=1)


def _save_state(state: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def weak_review_ids(connection: sqlite3.Connection, limit: int = 20) -> list[str]:
    """「直近の回答が不正解だった」語のreview_idを新しい順に返す（重複なし）。

    同じreview_idに複数回答があっても最新の1件だけを見る。最新が正解に変わっていれば
    対象から外れる（一度克服した語をいつまでも「苦手」扱いし続けないため）。

    語彙のreview_idは `toeic.words1-400.*` / `toeic.supplement1.*` など出典によって
    プレフィックスが揃っていないため、review_idの文字列パターンでは絞り込まず、
    load_pool()と同じく generated_item.kind = 'vocab' で判定する。
    """
    rows = connection.execute(
        """
        SELECT a.review_id FROM attempt a
        JOIN generated_item g ON g.review_id = a.review_id
        WHERE g.kind = 'vocab'
          AND a.created_at = (
              SELECT MAX(created_at) FROM attempt b WHERE b.review_id = a.review_id
          )
          AND a.correct = 0
        ORDER BY a.created_at DESC
        """
    ).fetchall()
    seen: dict[str, None] = {}
    for row in rows:
        seen.setdefault(row["review_id"], None)
    return list(seen)[:limit]


def next_batch(
    pool: list[VocabEntry],
    count: int,
    home: Path | None = None,
    weak_ids: list[str] | None = None,
) -> tuple[list[VocabEntry], dict]:
    """未出題の語を順に count 件取り出し、状態を1回分進める。

    呼ぶたびに読み進み位置が進むため、同じ日に2回呼ぶと別のバッチが返る
    （worksheetの作り直しで同じ語を出したい場合は、直前に保存したitems.jsonを再利用する）。

    weak_ids が渡された場合、その語を優先的にバッチへ混ぜる（残りをローテーションで
    埋める。cursorはローテーションで実際に消費した分だけ進む — weak_ids側の消費では
    進めない。weak_ids由来の語と同じ語がローテーション側でも選ばれそうになった場合は
    スキップして次へ進む、二重出題を避けるため）。出題順で「これは復習」と分からない
    よう、最後に全体をシャッフルする。
    """
    by_id = {entry.review_id: entry for entry in pool}
    weak_selected = [rid for rid in (weak_ids or []) if rid in by_id][:count]

    path = _state_path(home)
    state = _load_state(list(by_id.keys()), path)

    order = state["order"]
    cursor = state["cursor"]
    cycle = state["cycle"]

    exclude = set(weak_selected)
    remaining_count = count - len(weak_selected)
    batch_ids: list[str] = []
    while len(batch_ids) < remaining_count:
        if cursor >= len(order):
            cycle += 1
            fresh = _fresh_shuffle(list(by_id.keys()), cycle)
            order, cursor = fresh["order"], fresh["cursor"]
        rid = order[cursor]
        cursor += 1
        if rid in exclude:
            continue
        batch_ids.append(rid)

    state = {"order": order, "cursor": cursor, "cycle": cycle}
    _save_state(state, path)

    combined_ids = weak_selected + batch_ids
    random.shuffle(combined_ids)
    batch = [by_id[rid] for rid in combined_ids]
    return batch, state


def build_choices(
    word: VocabEntry, pool: list[VocabEntry], n_choices: int = 4
) -> tuple[list[str], int]:
    """正解1つ＋プールの他の語の意味からランダムな誤答を組み立てる。"""
    distractor_pool = [
        entry for entry in pool
        if entry.review_id != word.review_id and entry.meaning != word.meaning
    ]
    distractors = random.sample(distractor_pool, k=min(n_choices - 1, len(distractor_pool)))
    choices = [word.meaning] + [d.meaning for d in distractors]
    random.shuffle(choices)
    answer_index = choices.index(word.meaning)
    return choices, answer_index
