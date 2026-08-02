"""SQLite（運用状態）の初期化とマイグレーション。

置き場所が `~/.academic-english/` なのは意図的で、academic-infra 自体が public
リポジトリだから。学習履歴・誤答・語彙は個人データなので、`.gitignore` に頼らず
そもそもリポジトリの外に出しておく。

Drive 同期フォルダ上では稼働させない（SQLite のロックがネットワーク同期と噛み合わない）。
バックアップは `backup()` が `sqlite3 .backup` 相当のスナップショットを取り、
`acenglish_cli.py backup --push` で private な `academic-english-data` リポジトリへ
commit する（正本はそちら。ここは運用中の実体が置いてあるだけ）。
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_HOME_ENV = "ACADEMIC_ENGLISH_HOME"
_DEFAULT_HOME = Path.home() / ".academic-english"

SCHEMA_VERSION = 3

_MIGRATIONS: dict[int, tuple[str, ...]] = {
    1: (
        """
        CREATE TABLE material (
            review_id     TEXT PRIMARY KEY,
            course_id     TEXT NOT NULL,
            title         TEXT NOT NULL,
            source_file   TEXT NOT NULL,
            section_file  TEXT,
            source_commit TEXT NOT NULL,
            updated_at    TEXT NOT NULL
        )
        """,
        """
        -- 生成物。`is_ephemeral` と `verified_at` を必須にしているのは、一時生成した
        -- 演習が検証済みの正式教材と混ざったまま溜まり続けるのを防ぐため。
        CREATE TABLE generated_item (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            kind           TEXT NOT NULL,
            review_id      TEXT NOT NULL,
            course_id      TEXT NOT NULL,
            payload        TEXT NOT NULL,
            difficulty     INTEGER NOT NULL,
            reason         TEXT NOT NULL,
            generated_by   TEXT NOT NULL,
            prompt_version TEXT NOT NULL,
            source_commit  TEXT NOT NULL,
            is_ephemeral   INTEGER NOT NULL DEFAULT 1,
            created_at     TEXT NOT NULL,
            verified_at    TEXT,
            retired_at     TEXT,
            FOREIGN KEY (review_id) REFERENCES material (review_id)
        )
        """,
        "CREATE INDEX idx_generated_item_review ON generated_item (review_id, kind)",
        """
        CREATE TABLE learning_session (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id  TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at   TEXT,
            note       TEXT
        )
        """,
        """
        -- 学習者モデルの更新根拠。正誤だけでなく所要時間・自信度・ヒント・再回答まで
        -- 残すのは、mastery を単純な正答率で表さないため（設計書 §8）。
        CREATE TABLE attempt (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL,
            item_id         INTEGER NOT NULL,
            review_id       TEXT NOT NULL,
            domain          TEXT NOT NULL,
            sub_skill       TEXT NOT NULL,
            response        TEXT,
            correct         INTEGER NOT NULL,
            elapsed_ms      INTEGER NOT NULL,
            self_confidence REAL,
            hint_used       INTEGER NOT NULL DEFAULT 0,
            retry_count     INTEGER NOT NULL DEFAULT 0,
            error_cause     TEXT,
            edit_distance   INTEGER,
            days_since_last REAL,
            created_at      TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES learning_session (id),
            FOREIGN KEY (item_id) REFERENCES generated_item (id)
        )
        """,
        "CREATE INDEX idx_attempt_review ON attempt (review_id, created_at)",
        """
        CREATE TABLE skill_state (
            domain         TEXT NOT NULL,
            sub_skill      TEXT NOT NULL,
            target_ref     TEXT NOT NULL,
            mastery        REAL NOT NULL,
            confidence     REAL NOT NULL,
            latency_ms_p50 INTEGER,
            hint_rate      REAL NOT NULL DEFAULT 0.0,
            retention_days REAL,
            error_streak   INTEGER NOT NULL DEFAULT 0,
            attempts       INTEGER NOT NULL DEFAULT 0,
            updated_at     TEXT NOT NULL,
            PRIMARY KEY (domain, sub_skill, target_ref)
        )
        """,
        """
        -- 間隔は goigoi (word.schema.json v1) と同じ SM-2。別アルゴリズムを混ぜると
        -- goigoi-data と同期したときに状態が壊れる。
        CREATE TABLE review_queue (
            item_id          INTEGER PRIMARY KEY,
            review_id        TEXT NOT NULL,
            interval         INTEGER NOT NULL DEFAULT 0,
            ease_factor      REAL NOT NULL DEFAULT 2.5,
            repetitions      INTEGER NOT NULL DEFAULT 0,
            next_review      TEXT NOT NULL,
            last_reviewed_at TEXT,
            FOREIGN KEY (item_id) REFERENCES generated_item (id)
        )
        """,
        "CREATE INDEX idx_review_queue_due ON review_queue (next_review)",
        """
        -- 資料への「追記候補」。ここはまだ Draft ですらない（ユーザー未確認）。
        -- 確認を経て findings.json になり、既存の promote_drive_comments.py が Issue 化する。
        CREATE TABLE revision_candidate (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            review_id   TEXT NOT NULL,
            course_id   TEXT NOT NULL,
            source_file TEXT NOT NULL,
            title       TEXT NOT NULL,
            problem     TEXT NOT NULL,
            fix_spec    TEXT NOT NULL,
            evidence    TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'open',
            created_at  TEXT NOT NULL,
            promoted_at TEXT
        )
        """,
    ),
    # v2: 科目資料以外（TOEIC語彙・VOA記事・TED字幕）も学習対象にできるようにする。
    # 外部素材には「直すべき科目資料」が無いので、還元先を候補ごとに持たせる。
    2: (
        "ALTER TABLE material ADD COLUMN source TEXT NOT NULL DEFAULT 'academic'",
        "ALTER TABLE material ADD COLUMN origin TEXT",
        "ALTER TABLE revision_candidate ADD COLUMN target_kind TEXT NOT NULL DEFAULT 'course_repo'",
        "CREATE INDEX idx_material_source ON material (source)",
    ),
    # v3: 回答直後に一度スケジュールし、答えを見たあとの自己申告で引き直す。
    # 引き直しは「もう一度進める」ではなく「同じ地点から計算し直す」でなければ
    # 間隔が二重に伸びるので、回答前の SM-2 状態を控えておく。
    3: ("ALTER TABLE attempt ADD COLUMN queue_state_before TEXT",),
}


def now_iso() -> str:
    """UTC の ISO8601（秒精度）。既存 manifest.py の generated_at と同じ形式に揃える。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_home() -> Path:
    override = os.environ.get(DEFAULT_HOME_ENV, "").strip()
    return Path(override) if override else _DEFAULT_HOME


def database_path(home: Path | None = None) -> Path:
    return (home or default_home()) / "english.db"


def connect(path: Path | None = None) -> sqlite3.Connection:
    """DB を開き、必要ならマイグレーションを流す。何度呼んでも安全。"""
    destination = path or database_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # 個人データなので、ディレクトリは本人のみ。既存ディレクトリにも都度かけ直す。
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
    """稼働中でも安全なスナップショットを取る。

    学習履歴は再生成できないので、private リポジトリへ定期コミットする前提。
    ファイルを cp するのではなく sqlite の backup API を使う（書き込み途中の
    コピーを掴まないため）。
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    with connect(source) as connection, sqlite3.connect(destination) as target:
        connection.backup(target)
    return destination
