"""毎日の単語テスト（語彙MCQ）用の出題ローテーション。

TOEIC語彙（`fetch-toeic` で取り込み済みの2,282語）は既に語義・例文を持っているため、
Part5/Part7と違い**生成は不要**。単語プールからの抽出・選択肢の組み立てだけで完結する
（決定論的コード。Claudeが文面を作る必要はない）。

「毎日ランダムに出すが、1サイクル（プール全体を1周し終える）までは同じ語を出さない」
という要件のため、単純な random.sample を毎回呼ぶのではなく、
シャッフルした順序と読み進めた位置（cursor）を状態として永続化する。
1周し終えたら再シャッフルして次のサイクルに入る。
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


def next_batch(
    pool: list[VocabEntry], count: int, home: Path | None = None
) -> tuple[list[VocabEntry], dict]:
    """未出題の語を順に count 件取り出し、状態を1回分進める。

    呼ぶたびに読み進み位置が進むため、同じ日に2回呼ぶと別のバッチが返る
    （worksheetの作り直しで同じ語を出したい場合は、直前に保存したitems.jsonを再利用する）。
    """
    by_id = {entry.review_id: entry for entry in pool}
    path = _state_path(home)
    state = _load_state(list(by_id.keys()), path)

    order = state["order"]
    cursor = state["cursor"]
    cycle = state["cycle"]

    batch_ids: list[str] = []
    while len(batch_ids) < count:
        if cursor >= len(order):
            cycle += 1
            fresh = _fresh_shuffle(list(by_id.keys()), cycle)
            order, cursor = fresh["order"], fresh["cursor"]
        remaining = count - len(batch_ids)
        take = order[cursor:cursor + remaining]
        batch_ids.extend(take)
        cursor += len(take)

    state = {"order": order, "cursor": cursor, "cycle": cycle}
    _save_state(state, path)

    batch = [by_id[rid] for rid in batch_ids]
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
