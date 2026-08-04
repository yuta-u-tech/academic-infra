"""SQLite（Core の運用状態）の初期化とマイグレーション。

置き場所が `~/.academic-infra/` なのは `acenglish/db.py` と同じ理由で、
academic-infra 自体が public リポジトリだから。Goal/Resource/Research の
運用データは個人の学習計画そのものなので、リポジトリの外に出しておく。

Evidence/Mastery（`attempt` / `skill_state` 等）はここには置かない。
`~/.academic-english/english.db` に残したまま、Core からは Domain Plugin
Interface 経由で参照する（設計書 §2.1）。
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_HOME_ENV = "ACADEMIC_INFRA_HOME"
_DEFAULT_HOME = Path.home() / ".academic-infra"

SCHEMA_VERSION = 1

_MIGRATIONS: dict[int, tuple[str, ...]] = {
    1: (
        """
        CREATE TABLE goal (
            goal_id            TEXT PRIMARY KEY,
            parent_goal_id     TEXT REFERENCES goal (goal_id),
            title              TEXT NOT NULL,
            target_value       TEXT,
            current_value      TEXT,
            deadline           TEXT,
            priority           INTEGER NOT NULL DEFAULT 3,
            evaluation_method  TEXT,
            status             TEXT NOT NULL DEFAULT 'active',
            created_at         TEXT NOT NULL,
            updated_at         TEXT NOT NULL
        )
        """,
        "CREATE INDEX idx_goal_parent ON goal (parent_goal_id)",
        """
        -- domain_ref は Domain Plugin 側の主キー（例: acenglish の
        -- (domain, sub_skill, target_ref)）を JSON 文字列で緩く持つ。
        -- 外部キーにしないのは、Plugin ごとに DB エンジン・スキーマが違うため。
        CREATE TABLE competency (
            competency_id         TEXT PRIMARY KEY,
            goal_id                TEXT NOT NULL REFERENCES goal (goal_id),
            domain_id              TEXT NOT NULL,
            parent_competency_id   TEXT REFERENCES competency (competency_id),
            title                  TEXT NOT NULL,
            domain_ref              TEXT,
            exam_weight             REAL,
            created_at              TEXT NOT NULL
        )
        """,
        "CREATE INDEX idx_competency_goal ON competency (goal_id)",
        """
        CREATE TABLE resource (
            resource_id    TEXT PRIMARY KEY,
            goal_id        TEXT NOT NULL REFERENCES goal (goal_id),
            title          TEXT NOT NULL,
            kind           TEXT NOT NULL,
            location       TEXT,
            status         TEXT NOT NULL DEFAULT 'candidate',
            authority      TEXT,
            created_at     TEXT NOT NULL,
            updated_at     TEXT NOT NULL
        )
        """,
        "CREATE INDEX idx_resource_goal ON resource (goal_id)",
        """
        CREATE TABLE resource_requirement (
            requirement_id  TEXT PRIMARY KEY,
            goal_id         TEXT NOT NULL REFERENCES goal (goal_id),
            competency_ids  TEXT NOT NULL,
            gap_kind        TEXT NOT NULL,
            priority        TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'unresolved',
            spec            TEXT NOT NULL,
            created_at      TEXT NOT NULL
        )
        """,
        "CREATE INDEX idx_resource_requirement_goal ON resource_requirement (goal_id)",
        """
        CREATE TABLE research_request (
            request_id  TEXT PRIMARY KEY,
            goal_id     TEXT NOT NULL REFERENCES goal (goal_id),
            kind        TEXT NOT NULL,
            trigger     TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'open',
            created_at  TEXT NOT NULL
        )
        """,
        "CREATE INDEX idx_research_request_goal ON research_request (goal_id)",
        """
        CREATE TABLE finding (
            finding_id     TEXT PRIMARY KEY,
            request_id     TEXT NOT NULL REFERENCES research_request (request_id),
            summary        TEXT NOT NULL,
            proposal_kind  TEXT NOT NULL,
            payload        TEXT NOT NULL,
            created_at     TEXT NOT NULL
        )
        """,
        "CREATE INDEX idx_finding_request ON finding (request_id)",
        """
        CREATE TABLE proposal (
            proposal_id  TEXT PRIMARY KEY,
            goal_id      TEXT NOT NULL REFERENCES goal (goal_id),
            tier         TEXT NOT NULL,
            kind         TEXT NOT NULL,
            payload      TEXT NOT NULL,
            status       TEXT NOT NULL DEFAULT 'pending',
            reason       TEXT,
            approved_by  TEXT,
            approved_at  TEXT,
            created_at   TEXT NOT NULL
        )
        """,
        "CREATE INDEX idx_proposal_goal ON proposal (goal_id)",
        """
        -- confidence は必須（NOT NULL にはしないが空文字を許さない）。
        -- 承認された変更の効果を相関のまま因果と断定しないため、常に確度を書かせる。
        CREATE TABLE intervention (
            intervention_id  TEXT PRIMARY KEY,
            goal_id          TEXT NOT NULL REFERENCES goal (goal_id),
            proposal_id      TEXT REFERENCES proposal (proposal_id),
            change_summary   TEXT NOT NULL,
            reason           TEXT NOT NULL,
            evidence_ref     TEXT,
            approved_by      TEXT,
            expected_effect  TEXT,
            actual_effect    TEXT,
            confidence       TEXT NOT NULL,
            created_at       TEXT NOT NULL
        )
        """,
        "CREATE INDEX idx_intervention_goal ON intervention (goal_id)",
    ),
}


def now_iso() -> str:
    """UTC の ISO8601（秒精度）。acenglish/db.py の now_iso() と同じ形式に揃える。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_home() -> Path:
    override = os.environ.get(DEFAULT_HOME_ENV, "").strip()
    return Path(override) if override else _DEFAULT_HOME


def database_path(home: Path | None = None) -> Path:
    return (home or default_home()) / "core.db"


def connect(path: Path | None = None) -> sqlite3.Connection:
    """DB を開き、必要ならマイグレーションを流す。何度呼んでも安全。"""
    destination = path or database_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.parent.chmod(0o700)

    connection = sqlite3.connect(destination)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
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
    """未適用のマイグレーションだけを流し、到達したバージョンを返す。"""
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


def backup(destination: Path, source: Path | None = None) -> Path:
    """稼働中でも安全なスナップショットを取る（acenglish/db.py の backup() と同型）。"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with connect(source) as connection, sqlite3.connect(destination) as target:
        connection.backup(target)
    return destination
