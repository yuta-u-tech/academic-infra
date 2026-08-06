"""統計検定準1級 学習ループのSQLite（個人データ）。

academic-infraはpublicリポジトリのため、acenglishの`~/.academic-english/`と同じ理由で
`~/.academic-toukei/`に置く（リポジトリの外）。10日という期限の性質上、acenglishのような
SM-2間隔反復・LaTeX冊子・Drive publishは持たない最小構成: 問題(problem)・解答記録(attempt)・
Competency別の習熟度(skill_state)の3テーブルのみ。
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_HOME_ENV = "ACADEMIC_TOUKEI_HOME"
_DEFAULT_HOME = Path.home() / ".academic-toukei"

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS problem (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        competency_id TEXT NOT NULL,
        question      TEXT NOT NULL,
        choices       TEXT NOT NULL,
        answer_index  INTEGER NOT NULL,
        explanation   TEXT NOT NULL,
        set_id        TEXT NOT NULL,
        created_at    TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_problem_competency ON problem (competency_id)",
    """
    CREATE TABLE IF NOT EXISTS attempt (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        problem_id    INTEGER NOT NULL,
        competency_id TEXT NOT NULL,
        chosen_index  INTEGER NOT NULL,
        correct       INTEGER NOT NULL,
        created_at    TEXT NOT NULL,
        FOREIGN KEY (problem_id) REFERENCES problem (id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_attempt_competency ON attempt (competency_id, created_at)",
    """
    CREATE TABLE IF NOT EXISTS skill_state (
        competency_id TEXT PRIMARY KEY,
        mastery       REAL NOT NULL,
        confidence    REAL NOT NULL,
        attempts      INTEGER NOT NULL DEFAULT 0,
        error_streak  INTEGER NOT NULL DEFAULT 0,
        updated_at    TEXT NOT NULL
    )
    """,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_home() -> Path:
    override = os.environ.get(DEFAULT_HOME_ENV, "").strip()
    return Path(override) if override else _DEFAULT_HOME


def database_path(home: Path | None = None) -> Path:
    return (home or default_home()) / "toukei.db"


def connect(path: Path | None = None) -> sqlite3.Connection:
    destination = path or database_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.parent.chmod(0o700)

    connection = sqlite3.connect(destination)
    connection.row_factory = sqlite3.Row
    for statement in _SCHEMA:
        connection.execute(statement)
    connection.commit()
    return connection
