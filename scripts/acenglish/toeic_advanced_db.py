"""『TOEIC上級単語.pdf』OCR取り込み専用のステージングDB。

`english.db`（本番、個人の学習履歴・~/.academic-english/ 配下）とはファイルごと
独立させてある。ただし置き場所は本番と違い、**academic-infaryリポジトリ直下**
（`.toeic-advanced-vocab/`、`.gitignore`済み）にする。理由は本番の語彙DBとは
性質が違うため:

- `english.db` は個人の学習履歴そのもの（誰の誤答か・いつ解いたか）なので
  publicリポジトリの外に完全に出す必要がある
- こちらは市販本からOCRで起こした「これから学習材料になる素材」で、academic-infra
  （このマージ作業をする場所）から直接見えている方が都合がよい。ただしOCR元は
  購入した書籍のコンテンツなので、git管理下（=GitHubでpublicに見える状態）には
  絶対に置かない。`.gitignore`でリポジトリ直下からは除外しつつ、ファイルシステム上は
  リポジトリの中に置く、という折衷にしてある

レビュー（pending→approved/rejected）を経て本番へマージしたら、
`private academic-english-data` 側へ移す想定（このモジュールはマージ処理も
その移動処理も持たない。まだ実装しない。Issue #9 の非スコープに明記済み）。
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_HOME_ENV = "TOEIC_ADVANCED_VOCAB_HOME"
DB_FILENAME = "staging-toeic-advanced.db"
_DEFAULT_HOME = Path(__file__).resolve().parent.parent.parent / ".toeic-advanced-vocab"

SCHEMA_VERSION = 1

_STATUSES = ("pending", "approved", "rejected", "merged")

_MIGRATIONS: dict[int, tuple[str, ...]] = {
    1: (
        """
        CREATE TABLE ocr_candidate (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            page_number      INTEGER NOT NULL,
            word             TEXT NOT NULL,
            part_of_speech   TEXT,
            meaning          TEXT NOT NULL,
            example          TEXT,
            ocr_confidence   REAL,
            needs_review     INTEGER NOT NULL DEFAULT 1,
            review_note      TEXT,
            dup_of_review_id TEXT,
            status           TEXT NOT NULL DEFAULT 'pending',
            created_at       TEXT NOT NULL,
            reviewed_at      TEXT
        )
        """,
        "CREATE INDEX idx_ocr_candidate_status ON ocr_candidate (status)",
        "CREATE INDEX idx_ocr_candidate_page ON ocr_candidate (page_number)",
    ),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_home() -> Path:
    override = os.environ.get(DEFAULT_HOME_ENV, "").strip()
    return Path(override) if override else _DEFAULT_HOME


def database_path(home: Path | None = None) -> Path:
    return (home or default_home()) / DB_FILENAME


def connect(path: Path | None = None) -> sqlite3.Connection:
    """DB を開き、必要ならマイグレーションを流す。何度呼んでも安全。"""
    destination = path or database_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.parent.chmod(0o700)

    connection = sqlite3.connect(destination)
    connection.row_factory = sqlite3.Row
    migrate(connection)
    return connection


def _current_version(connection: sqlite3.Connection) -> int:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    row = connection.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
    return row["v"] or 0


def migrate(connection: sqlite3.Connection) -> int:
    version = _current_version(connection)
    for target in sorted(v for v in _MIGRATIONS if v > version):
        for statement in _MIGRATIONS[target]:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (target, now_iso()),
        )
        version = target
    connection.commit()
    return version


def add_candidate(
    connection: sqlite3.Connection,
    *,
    page_number: int,
    word: str,
    meaning: str,
    part_of_speech: str | None = None,
    example: str | None = None,
    ocr_confidence: float | None = None,
) -> int:
    """OCR結果（またはOCR前の手動確認分）を1件、pending状態で追加する。"""
    cursor = connection.execute(
        "INSERT INTO ocr_candidate (page_number, word, part_of_speech, meaning, example,"
        " ocr_confidence, needs_review, status, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, 1, 'pending', ?)",
        (page_number, word, part_of_speech, meaning, example, ocr_confidence, now_iso()),
    )
    connection.commit()
    return cursor.lastrowid


def set_review(
    connection: sqlite3.Connection,
    candidate_id: int,
    *,
    status: str,
    review_note: str | None = None,
    dup_of_review_id: str | None = None,
) -> None:
    """レビュー結果を記録する。status は approved/rejected のいずれか（mergedは本番マージ実装側が付ける）。"""
    if status not in _STATUSES:
        raise ValueError(f"status は {_STATUSES} のいずれかである必要があります: {status!r}")
    connection.execute(
        "UPDATE ocr_candidate SET status = ?, review_note = ?, dup_of_review_id = ?,"
        " needs_review = 0, reviewed_at = ? WHERE id = ?",
        (status, review_note, dup_of_review_id, now_iso(), candidate_id),
    )
    connection.commit()


def list_candidates(
    connection: sqlite3.Connection, *, status: str | None = None
) -> list[sqlite3.Row]:
    if status is None:
        return connection.execute(
            "SELECT * FROM ocr_candidate ORDER BY page_number, id"
        ).fetchall()
    return connection.execute(
        "SELECT * FROM ocr_candidate WHERE status = ? ORDER BY page_number, id", (status,)
    ).fetchall()


def stats(connection: sqlite3.Connection) -> dict[str, int]:
    rows = connection.execute(
        "SELECT status, COUNT(*) AS n FROM ocr_candidate GROUP BY status"
    ).fetchall()
    return {row["status"]: row["n"] for row in rows}
