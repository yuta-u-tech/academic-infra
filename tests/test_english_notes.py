"""外部素材の誤答 → english-notes の drafts/。

要点は2つ。科目リポジトリへ無関係な Issue を立てないこと、`notes/` を勝手に書き換えないこと。
"""

import pytest

from acenglish import generate, notes, promote, study
from acenglish.db import connect
from acenglish.items import GeneratedItem, GenerationResult, VocabItem
from acenglish.sources.base import ExternalMaterial

TOEIC = ExternalMaterial(
    review_id="toeic.words1-400.0001",
    source="toeic",
    title="anyway",
    body="anyway\nとにかく",
    origin="yuta-u-tech/study-forge:data/words1-400.json#1",
    source_file="notes/vocabulary/toeic-words1-400.md",
    source_commit="words1-400",
    chapter_title="words1-400",
)


def _result() -> GenerationResult:
    return GenerationResult(
        review_id=TOEIC.review_id,
        course_id=TOEIC.course_id,
        source_commit=TOEIC.source_commit,
        generated_by="studyforge",
        prompt_version="import-1",
        is_ephemeral=False,
        items=[
            GeneratedItem(
                difficulty=3,
                reason="TOEIC 単語集からの取り込み",
                item=VocabItem(word="anyway", meaning="とにかく", example="Anyway, let's try."),
            )
        ],
    )


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "english-notes"
    (root / ".git").mkdir(parents=True)
    return root


@pytest.fixture
def db(tmp_path):
    connection = connect(tmp_path / "english.db")
    generate.upsert_material(connection, TOEIC)
    yield connection
    connection.close()


def _fail_three_times(db) -> None:
    item_id = generate.ingest(db, _result())[0]
    session_id = study.start_session(db, TOEIC.course_id)
    for _ in range(3):
        study.answer(db, session_id, item_id, "wrong", elapsed_ms=4_000)


def test_external_material_records_where_it_came_from(db):
    row = db.execute("SELECT * FROM material WHERE review_id = ?", (TOEIC.review_id,)).fetchone()
    assert row["source"] == "toeic"
    assert row["origin"].startswith("yuta-u-tech/study-forge")


def test_repeated_failures_target_the_note_not_the_course_repo(db):
    _fail_three_times(db)
    row = db.execute("SELECT * FROM revision_candidate").fetchone()
    assert row["target_kind"] == "english_note"
    assert row["source_file"] == "notes/vocabulary/toeic-words1-400.md"


def test_note_candidates_never_leak_into_course_issues(db, tmp_path):
    """TOEIC の誤答で科目リポジトリに Issue が立ったら事故。"""
    _fail_three_times(db)
    _, ids = promote.export_findings(db, tmp_path / "findings.json")
    assert ids == []
    assert promote.open_candidates(db) == []


def test_a_draft_is_written_for_review(db, repo):
    _fail_three_times(db)
    written = notes.write_drafts(db, repo)

    assert len(written) == 1
    assert written[0].parent == repo / "drafts"
    text = written[0].read_text(encoding="utf-8")
    assert "toeic.words1-400.0001" in text
    assert "3回連続" in text


def test_drafts_do_not_touch_the_published_notes(db, repo):
    """既存ノートを無断で書き換えない、は科目資料と同じ原則。"""
    published = repo / "notes" / "vocabulary"
    published.mkdir(parents=True)
    note = published / "toeic-words1-400.md"
    note.write_text("# 既存の内容\n", encoding="utf-8")

    _fail_three_times(db)
    notes.write_drafts(db, repo)

    assert note.read_text(encoding="utf-8") == "# 既存の内容\n"


def test_the_draft_leaves_the_thinking_to_the_human(db, repo):
    """機械が書けるのは「何をなぜ書き足すか」まで。理由と例文は本人が埋める。"""
    _fail_three_times(db)
    text = notes.write_drafts(db, repo)[0].read_text(encoding="utf-8")
    assert "自分の言葉で（ここを埋める）" in text
    assert "- [ ] 上を埋めた" in text


def test_writing_a_draft_does_not_close_the_candidate(db, repo):
    _fail_three_times(db)
    notes.write_drafts(db, repo)
    assert notes.open_note_candidates(db)

    notes.write_drafts(db, repo, mark=True)
    assert notes.open_note_candidates(db) == []


def test_a_wrong_notes_directory_is_refused(db, tmp_path):
    """関係ないディレクトリに drafts/ を作って散らかさない。"""
    _fail_three_times(db)
    with pytest.raises(notes.NotesRepositoryError, match="ENGLISH_NOTES_HOME"):
        notes.write_drafts(db, tmp_path / "not-a-repo")


def test_the_notes_location_can_be_overridden(monkeypatch, tmp_path):
    monkeypatch.setenv(notes.DEFAULT_NOTES_ENV, str(tmp_path / "elsewhere"))
    assert notes.notes_home() == tmp_path / "elsewhere"


def test_academic_material_still_goes_to_the_course_repo(db, tmp_path, repo):
    """外部素材を足したことで、科目資料側の経路が壊れていないこと。"""
    from tests.test_english_loop import TARGET, _result as academic_result

    generate.upsert_material(db, TARGET)
    item_id = generate.ingest(db, academic_result())[0]
    session_id = study.start_session(db, "dsa")
    for _ in range(3):
        study.answer(db, session_id, item_id, "wrong answer", elapsed_ms=4_000)

    _, ids = promote.export_findings(db, tmp_path / "findings.json", "dsa")
    assert len(ids) == 1
    assert notes.write_drafts(db, repo) == []
