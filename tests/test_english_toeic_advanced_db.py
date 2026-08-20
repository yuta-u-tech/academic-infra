"""TOEIC上級単語OCRステージングDB: 本番DBとファイルが独立していること、レビュー遷移が記録されること。"""

from pathlib import Path

from acenglish.toeic_advanced_db import (
    DB_FILENAME,
    DEFAULT_HOME_ENV,
    SCHEMA_VERSION,
    add_candidate,
    connect,
    database_path,
    default_home,
    detect_duplicates,
    list_candidates,
    merge_approved,
    migrate,
    set_review,
    stats,
)
from acenglish.db import connect as connect_english
from acenglish.generate import ingest, upsert_material
from acenglish.items import GeneratedItem, GenerationResult, VocabItem
from acenglish.sources.base import ExternalMaterial

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_the_staging_database_is_a_separate_file_from_the_production_database(monkeypatch, tmp_path):
    monkeypatch.setenv(DEFAULT_HOME_ENV, str(tmp_path))
    assert database_path().name == DB_FILENAME
    assert database_path().name != "english.db"


def test_the_default_location_is_inside_this_repository_and_gitignored(monkeypatch):
    """english.db と違い、これは購入書籍からのOCR素材＝academic-infra側で作業を続けるものなので、
    本番のように完全にリポジトリ外へ出す必要はない。ただしgit管理下には置かない。"""
    monkeypatch.delenv(DEFAULT_HOME_ENV, raising=False)
    assert default_home() == REPO_ROOT / ".toeic-advanced-vocab"
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".toeic-advanced-vocab/" in gitignore


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


def _seed_vocab(connection, review_id: str, word: str, meaning: str = "既存語") -> None:
    material = ExternalMaterial(
        review_id=review_id,
        source="toeic",
        title=word,
        body=f"{word}\n{meaning}",
        origin="test",
        source_file="notes/vocabulary/toeic.md",
        source_commit="test",
        chapter_title="test",
    )
    upsert_material(connection, material)
    ingest(
        connection,
        GenerationResult(
            review_id=review_id,
            course_id="english",
            source_commit="test",
            generated_by="test",
            prompt_version="test",
            is_ephemeral=False,
            items=[
                GeneratedItem(
                    difficulty=3,
                    reason="test",
                    item=VocabItem(word=word, meaning=meaning),
                )
            ],
        ),
    )


def test_detect_duplicates_marks_candidates_with_the_existing_review_id(tmp_path):
    staging = connect(tmp_path / DB_FILENAME)
    production = connect_english(tmp_path / "english.db")
    _seed_vocab(production, "toeic.words1-400.0001", "Cashier")
    candidate_id = add_candidate(staging, page_number=1, word="cashier", meaning="レジ係")

    result = detect_duplicates(staging, production)
    row = staging.execute("SELECT * FROM ocr_candidate WHERE id = ?", (candidate_id,)).fetchone()
    staging.close()
    production.close()

    assert result["detected"] == 1
    assert row["dup_of_review_id"] == "toeic.words1-400.0001"
    assert row["status"] == "pending"


def test_merge_approved_imports_non_duplicate_candidates_and_marks_them_merged(tmp_path):
    staging = connect(tmp_path / DB_FILENAME)
    production = connect_english(tmp_path / "english.db")
    candidate_id = add_candidate(
        staging,
        page_number=12,
        word="aberration",
        meaning="逸脱、異常",
        part_of_speech="n.",
        example="a temporary aberration",
    )
    set_review(staging, candidate_id, status="approved")

    result = merge_approved(staging, production)
    staged = staging.execute("SELECT * FROM ocr_candidate WHERE id = ?", (candidate_id,)).fetchone()
    material = production.execute(
        "SELECT * FROM material WHERE review_id = ?", ("toeic.toeic-advanced-vocab.0001",)
    ).fetchone()
    generated = production.execute(
        "SELECT * FROM generated_item WHERE review_id = ? AND kind = 'vocab'",
        ("toeic.toeic-advanced-vocab.0001",),
    ).fetchone()
    staging.close()
    production.close()

    assert result == {
        "approved_checked": 1,
        "merged": 1,
        "skipped_duplicate": 0,
        "skipped_existing": 0,
    }
    assert staged["status"] == "merged"
    assert staged["merged_review_id"] == "toeic.toeic-advanced-vocab.0001"
    assert material["source"] == "toeic"
    assert material["origin"] == "toeic-advanced-vocab:page-12#candidate-1"
    assert generated["generated_by"] == "import:toeic-advanced-vocab"


def test_merge_approved_skips_candidates_that_now_duplicate_production(tmp_path):
    staging = connect(tmp_path / DB_FILENAME)
    production = connect_english(tmp_path / "english.db")
    _seed_vocab(production, "toeic.personal-notes.0001", "cashier")
    candidate_id = add_candidate(staging, page_number=1, word="Cashier", meaning="レジ係")
    set_review(staging, candidate_id, status="approved")

    result = merge_approved(staging, production)
    row = staging.execute("SELECT * FROM ocr_candidate WHERE id = ?", (candidate_id,)).fetchone()
    merged_rows = production.execute(
        "SELECT COUNT(*) AS n FROM generated_item WHERE review_id LIKE 'toeic.toeic-advanced-vocab.%'"
    ).fetchone()["n"]
    staging.close()
    production.close()

    assert result["merged"] == 0
    assert result["skipped_duplicate"] == 1
    assert row["status"] == "approved"
    assert row["dup_of_review_id"] == "toeic.personal-notes.0001"
    assert merged_rows == 0
