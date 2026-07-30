"""SQLite: 個人データを public リポジトリの外へ置くこと、初期化が冪等であること。"""

import sqlite3
import stat

import pytest

from acenglish.db import (
    DEFAULT_HOME_ENV,
    SCHEMA_VERSION,
    backup,
    connect,
    database_path,
    default_home,
    migrate,
)

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent


def test_the_database_lives_outside_this_public_repository(monkeypatch):
    """academic-infra は public。学習履歴を .gitignore 頼みで中に置かない。"""
    monkeypatch.delenv(DEFAULT_HOME_ENV, raising=False)
    assert default_home() == __import__("pathlib").Path.home() / ".academic-english"
    assert REPO_ROOT not in database_path().parents


def test_the_location_can_be_overridden_for_tests(monkeypatch, tmp_path):
    monkeypatch.setenv(DEFAULT_HOME_ENV, str(tmp_path))
    assert database_path() == tmp_path / "english.db"


def test_the_database_directory_is_private(tmp_path):
    path = tmp_path / "home" / "english.db"
    connect(path).close()
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_connecting_twice_does_not_re_run_migrations(tmp_path):
    path = tmp_path / "english.db"
    first = connect(path)
    assert migrate(first) == SCHEMA_VERSION
    first.close()

    second = connect(path)
    assert migrate(second) == SCHEMA_VERSION
    rows = second.execute("SELECT COUNT(*) AS n FROM schema_migrations").fetchone()["n"]
    second.close()
    assert rows == SCHEMA_VERSION


def test_foreign_keys_are_enforced(tmp_path):
    """出所の分からない attempt が入ると、誤答分析の根拠が壊れる。"""
    with connect(tmp_path / "english.db") as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO attempt (session_id, item_id, review_id, domain, sub_skill,"
                " correct, elapsed_ms, created_at) VALUES (1, 1, 'x', 'vocabulary', 'recall',"
                " 1, 100, '2026-07-30T00:00:00+00:00')"
            )


def test_backup_produces_a_readable_snapshot(tmp_path):
    source = tmp_path / "english.db"
    with connect(source) as connection:
        connection.execute(
            "INSERT INTO material (review_id, course_id, title, source_file, section_file,"
            " source_commit, updated_at) VALUES ('a.b.c', 'dsa', 't', 'f.tex', 's.md', 'abc',"
            " '2026-07-30T00:00:00+00:00')"
        )
        connection.commit()

    destination = backup(tmp_path / "snapshots" / "english.db", source)
    with sqlite3.connect(destination) as snapshot:
        assert snapshot.execute("SELECT COUNT(*) FROM material").fetchone()[0] == 1
