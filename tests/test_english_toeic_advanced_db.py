"""TOEIC上級単語OCRステージングDB: 本番DBとファイルが独立していること、レビュー遷移が記録されること。"""

from pathlib import Path

from acenglish.toeic_advanced_db import (
    DB_FILENAME,
    SCHEMA_VERSION,
    add_candidate,
    connect,
    database_path,
    list_candidates,
    migrate,
    set_review,
    stats,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_the_staging_database_is_a_separate_file_from_the_production_database(monkeypatch, tmp_path):
    monkeypatch.setenv("ACADEMIC_ENGLISH_HOME", str(tmp_path))
    assert database_path().name == DB_FILENAME
    assert database_path().name != "english.db"


def test_connecting_twice_does_not_re_run_migrations(tmp_path):
    path = tmp_path / DB_FILENAME
    first = connect(path)
    assert migrate(first) == SCHEMA_VERSION
    first.close()

    second = connect(path)
    assert migrate(second) == SCHEMA_VERSION
    rows = second.execute("SELECT COUNT(*) AS n FROM schema_migrations").fetchone()["n"]
    second.close()
    assert rows == SCHEMA_VERSION


def test_added_candidates_start_as_pending_and_need_review(tmp_path):
    connection = connect(tmp_path / DB_FILENAME)
    candidate_id = add_candidate(
        connection, page_number=12, word="aberration", meaning="逸脱、異常",
        part_of_speech="n.", example="a temporary aberration",
    )
    connection.close()

    connection = connect(tmp_path / DB_FILENAME)
    row = list_candidates(connection, status="pending")[0]
    connection.close()

    assert row["id"] == candidate_id
    assert row["page_number"] == 12
    assert row["needs_review"] == 1
    assert row["status"] == "pending"
    assert row["reviewed_at"] is None


def test_review_moves_a_candidate_out_of_pending_and_records_a_note(tmp_path):
    connection = connect(tmp_path / DB_FILENAME)
    candidate_id = add_candidate(connection, page_number=1, word="cashier", meaning="レジ係")
    set_review(connection, candidate_id, status="rejected", review_note="OCR誤読")
    connection.close()

    connection = connect(tmp_path / DB_FILENAME)
    pending = list_candidates(connection, status="pending")
    rejected = list_candidates(connection, status="rejected")
    connection.close()

    assert pending == []
    assert len(rejected) == 1
    assert rejected[0]["review_note"] == "OCR誤読"
    assert rejected[0]["needs_review"] == 0
    assert rejected[0]["reviewed_at"] is not None


def test_stats_counts_candidates_by_status(tmp_path):
    connection = connect(tmp_path / DB_FILENAME)
    a = add_candidate(connection, page_number=1, word="a", meaning="a")
    add_candidate(connection, page_number=1, word="b", meaning="b")
    set_review(connection, a, status="approved")
    connection.close()

    connection = connect(tmp_path / DB_FILENAME)
    result = stats(connection)
    connection.close()

    assert result == {"pending": 1, "approved": 1}
