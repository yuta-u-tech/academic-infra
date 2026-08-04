"""SQLite: 個人の学習計画を public リポジトリの外へ置くこと、初期化が冪等であること。"""

import sqlite3
import stat
from pathlib import Path

import pytest

from acinfra_core.db import (
    DEFAULT_HOME_ENV,
    SCHEMA_VERSION,
    backup,
    connect,
    database_path,
    default_home,
    migrate,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_the_database_lives_outside_this_public_repository(monkeypatch):
    monkeypatch.delenv(DEFAULT_HOME_ENV, raising=False)
    assert default_home() == Path.home() / ".academic-infra"
    assert REPO_ROOT not in database_path().parents


def test_the_location_can_be_overridden_for_tests(monkeypatch, tmp_path):
    monkeypatch.setenv(DEFAULT_HOME_ENV, str(tmp_path))
    assert database_path() == tmp_path / "core.db"


def test_the_database_directory_is_private(tmp_path):
    path = tmp_path / "home" / "core.db"
    connect(path).close()
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_connecting_twice_does_not_re_run_migrations(tmp_path):
    path = tmp_path / "core.db"
    first = connect(path)
    assert migrate(first) == SCHEMA_VERSION
    first.close()

    second = connect(path)
    assert migrate(second) == SCHEMA_VERSION
    rows = second.execute("SELECT COUNT(*) AS n FROM schema_migrations").fetchone()["n"]
    second.close()
    assert rows == SCHEMA_VERSION


def test_foreign_keys_are_enforced(tmp_path):
    """出所の分からない competency が入ると、Goal との対応が壊れる。"""
    with connect(tmp_path / "core.db") as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO competency (competency_id, goal_id, domain_id, title, created_at)"
                " VALUES ('toeic.part7', 'no-such-goal', 'toeic', 'Part7', '2026-08-04T00:00:00+00:00')"
            )


def test_backup_produces_a_readable_snapshot(tmp_path):
    source = tmp_path / "core.db"
    with connect(source) as connection:
        connection.execute(
            "INSERT INTO goal (goal_id, title, priority, status, created_at, updated_at)"
            " VALUES ('toeic-900', 'TOEIC 900', 3, 'active', '2026-08-04T00:00:00+00:00',"
            " '2026-08-04T00:00:00+00:00')"
        )
        connection.commit()

    destination = backup(tmp_path / "snapshots" / "core.db", source)
    with sqlite3.connect(destination) as snapshot:
        assert snapshot.execute("SELECT COUNT(*) FROM goal").fetchone()[0] == 1
