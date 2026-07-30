"""教材生成の「器」。中身の判断は Claude が行う。

academic-infra の既存フロー（Drive コメント → Claude が findings.json を書く →
スクリプトが機械的に Issue 化）と同じ思想で作る。どの語を選ぶか・どんな設問にするかは
決定論コードでは書けないので、ここは

    request()  資料本文と制約をまとめた依頼ファイルを出す
    ingest()   Claude が書いた結果を検証して DB に入れる

の2つだけを担う。生成そのものを LLM API へ投げるコードはここに置かない
（pm-desk では Claude 自身が生成器であり、外部サービスを前提にしない — 要件 §15）。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .db import now_iso
from .items import GenerationResult
from .target import LearningTarget

PROMPT_DIR = Path(__file__).resolve().parent.parent.parent / "english" / "prompts"
PROMPT_VERSION = "2026-07-30.1"

_KIND_PROMPTS = {
    "vocab": "vocab.md",
    "reading": "reading.md",
}


class UnknownKindError(Exception):
    pass


def request(target: LearningTarget, kinds: list[str], count: int = 5) -> dict:
    """Claude へ渡す生成依頼。資料本文と、生成物に必須の出所情報を同梱する。"""
    unknown = [k for k in kinds if k not in _KIND_PROMPTS]
    if unknown:
        raise UnknownKindError(
            f"未対応の種別: {', '.join(unknown)}（対応: {', '.join(sorted(_KIND_PROMPTS))}）"
        )

    return {
        "schema_version": 1,
        "prompt_version": PROMPT_VERSION,
        "instructions": [
            f"{PROMPT_DIR / _KIND_PROMPTS[kind]} の指示に従って {kind} を生成する"
            for kind in kinds
        ],
        "output_schema": "english/schema/generation-result.schema.json",
        "count_per_kind": count,
        "target": {
            "review_id": target.review_id,
            "course_id": target.course_id,
            "title": target.title,
            "chapter_title": target.chapter_title,
            "source_file": target.source_file,
            "section_file": target.section_file,
            "source_commit": target.source_commit,
        },
        "material": target.body,
    }


def write_request(target: LearningTarget, kinds: list[str], destination: Path, count: int = 5) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(request(target, kinds, count), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def load_result(path: Path) -> GenerationResult:
    """Claude が書いた生成結果を読み、スキーマ違反ならここで落とす。"""
    return GenerationResult.model_validate_json(path.read_text(encoding="utf-8"))


def upsert_material(connection: sqlite3.Connection, target: LearningTarget) -> None:
    """学習対象の資料メタデータを記録する。本文は持たない（正本は git 側）。"""
    connection.execute(
        """
        INSERT INTO material (review_id, course_id, title, source_file, section_file, source_commit, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (review_id) DO UPDATE SET
            title = excluded.title,
            source_file = excluded.source_file,
            section_file = excluded.section_file,
            source_commit = excluded.source_commit,
            updated_at = excluded.updated_at
        """,
        (
            target.review_id,
            target.course_id,
            target.title,
            target.source_file,
            target.section_file,
            target.source_commit,
            now_iso(),
        ),
    )
    connection.commit()


def ingest(connection: sqlite3.Connection, result: GenerationResult) -> list[int]:
    """検証済みの生成物を DB に入れ、作った item_id を返す。

    material 行が無ければ入れない（外部キー）。呼び出し側が先に `upsert_material()` する。
    """
    item_ids: list[int] = []
    for entry in result.items:
        cursor = connection.execute(
            """
            INSERT INTO generated_item (
                kind, review_id, course_id, payload, difficulty, reason,
                generated_by, prompt_version, source_commit, is_ephemeral, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.item.kind,
                result.review_id,
                result.course_id,
                entry.item.model_dump_json(),
                entry.difficulty,
                entry.reason,
                result.generated_by,
                result.prompt_version,
                result.source_commit,
                1 if result.is_ephemeral else 0,
                now_iso(),
            ),
        )
        item_ids.append(int(cursor.lastrowid))
    connection.commit()
    return item_ids


def retire_stale(connection: sqlite3.Connection, review_id: str, current_commit: str) -> int:
    """資料が更新されたら、古い版から作られた未検証の一時生成物を退役させる。

    検証済み（`verified_at` あり）のものは残す。人手で確認した教材まで勝手に消さない。
    """
    cursor = connection.execute(
        """
        UPDATE generated_item SET retired_at = ?
        WHERE review_id = ? AND source_commit != ? AND retired_at IS NULL
          AND is_ephemeral = 1 AND verified_at IS NULL
        """,
        (now_iso(), review_id, current_commit),
    )
    connection.commit()
    return cursor.rowcount
