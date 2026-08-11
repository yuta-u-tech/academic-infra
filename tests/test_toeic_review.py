"""間違えたTOEIC問題を1つの復習ノートにまとめる（toeic_review.py）。

要点: (1) 今も間違えたままのものだけを載せる。後で正解した問題は消える。
(2) review_id で重複しない。(3) 手作業で書いた目次(動画リンク等)は書き換えない。
"""

import pytest

from acenglish import generate, study, toeic_review
from acenglish.db import connect
from acenglish.items import GeneratedItem, GenerationResult, GrammarItem, VocabItem
from acenglish.notes import NotesRepositoryError
from acenglish.sources.base import ExternalMaterial

PART5 = ExternalMaterial(
    review_id="toeic.part5.20260810.0001",
    source="toeic",
    title="part5",
    body="",
    origin="toeic-forms",
    source_file="notes/grammar/toeic-part5.md",
    source_commit="20260810",
    chapter_title="part5",
)

VOCAB = ExternalMaterial(
    review_id="toeic.words1-400.0006",
    source="toeic",
    title="vocab",
    body="",
    origin="study-forge",
    source_file="notes/vocabulary/toeic-words1-400.md",
    source_commit="words1-400",
    chapter_title="words1-400",
)


def _grammar_result() -> GenerationResult:
    return GenerationResult(
        review_id=PART5.review_id,
        course_id=PART5.course_id,
        source_commit=PART5.source_commit,
        generated_by="toeic_forms",
        prompt_version="import-1",
        is_ephemeral=False,
        items=[
            GeneratedItem(
                difficulty=3,
                reason="Part5 空所補充",
                item=GrammarItem(
                    sentence="The manager ____ the report yesterday.",
                    choices=["reviewed", "review", "reviewing", "reviews"],
                    answer_index=0,
                    explanation="過去の出来事なので過去形。",
                    point="動詞の時制",
                    pattern="A",
                    pattern_note="同じ語の別の形",
                ),
            )
        ],
    )


def _vocab_result() -> GenerationResult:
    return GenerationResult(
        review_id=VOCAB.review_id,
        course_id=VOCAB.course_id,
        source_commit=VOCAB.source_commit,
        generated_by="studyforge",
        prompt_version="import-1",
        is_ephemeral=False,
        items=[
            GeneratedItem(
                difficulty=3,
                reason="TOEIC 単語集からの取り込み",
                item=VocabItem(word="division", meaning="部門", example="the HR division"),
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
    generate.upsert_material(connection, PART5)
    generate.upsert_material(connection, VOCAB)
    yield connection
    connection.close()


def _answer(db, target, result, correct_answers):
    item_id = generate.ingest(db, result)[0]
    session_id = study.start_session(db, target.course_id)
    for response in correct_answers:
        study.answer(db, session_id, item_id, response, elapsed_ms=4_000)
    return item_id


def test_a_currently_wrong_item_is_listed(db, repo):
    _answer(db, PART5, _grammar_result(), ["1"])  # 不正解(正解はindex 0)
    path = toeic_review.write_review(db, repo)

    text = path.read_text(encoding="utf-8")
    assert "toeic.part5.20260810.0001" in text
    assert "Part5（文法）" in text
    assert "The manager" in text


def test_an_item_later_answered_correctly_disappears(db, repo):
    _answer(db, PART5, _grammar_result(), ["1", "0"])  # 不正解 → 後で正解
    path = toeic_review.write_review(db, repo)

    text = path.read_text(encoding="utf-8")
    assert "toeic.part5.20260810.0001" not in text
    assert "現在、間違えたまま残っている問題はありません" in text


def test_multiple_domains_are_grouped(db, repo):
    _answer(db, PART5, _grammar_result(), ["1"])
    _answer(db, VOCAB, _vocab_result(), ["wrong"])
    path = toeic_review.write_review(db, repo)

    text = path.read_text(encoding="utf-8")
    assert "Part5（文法）" in text
    assert "語彙" in text
    assert "division" in text


def test_rerunning_does_not_duplicate_entries(db, repo):
    _answer(db, PART5, _grammar_result(), ["1"])
    toeic_review.write_review(db, repo)
    path = toeic_review.write_review(db, repo)

    text = path.read_text(encoding="utf-8")
    assert text.count("toeic.part5.20260810.0001") == 1


def test_a_hand_written_table_of_contents_survives_rebuild(db, repo):
    misc = repo / "TOEIC_MISC"
    misc.mkdir(parents=True)
    (misc / "toeic-review.md").write_text(
        "# TOEIC 復習ノート\n\n"
        "## 目次\n\n- 復習動画プレイリスト: https://youtube.com/playlist?list=abc123\n\n"
        f"{toeic_review._BEGIN_MARKER}\n\n(古い内容)\n\n{toeic_review._END_MARKER}\n",
        encoding="utf-8",
    )

    _answer(db, PART5, _grammar_result(), ["1"])
    path = toeic_review.write_review(db, repo)

    text = path.read_text(encoding="utf-8")
    assert "https://youtube.com/playlist?list=abc123" in text
    assert "(古い内容)" not in text
    assert "toeic.part5.20260810.0001" in text


def test_a_wrong_notes_directory_is_refused(db, tmp_path):
    with pytest.raises(NotesRepositoryError, match="ENGLISH_NOTES_HOME"):
        toeic_review.write_review(db, tmp_path / "not-a-repo")
