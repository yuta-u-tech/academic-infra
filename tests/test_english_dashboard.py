"""ダッシュボード集計。既存テーブルの読み出しだけで組み立てられることを固定する。"""

import pytest

from acenglish import dashboard, generate, study
from acenglish.db import connect
from acenglish.items import GenerationResult
from acenglish.target import LearningTarget

TARGET = LearningTarget(
    review_id="english.dashboard.s01",
    course_id="english",
    title="dashboard fixture",
    chapter_title="dashboard fixture",
    source_file="src/dashboard.tex",
    section_file="sections/dashboard.md",
    source_commit="abc123",
    body="dashboard fixture body",
)

OTHER_TARGET = LearningTarget(
    review_id="dsa.ch02.list.s01",
    course_id="dsa",
    title="線形リスト",
    chapter_title="リスト構造",
    source_file="src/chapters/ch02.tex",
    section_file="sections/ch02-01.md",
    source_commit="abc123",
    body="# 線形リスト\n\n先頭から順にたどる。",
)


def _result() -> GenerationResult:
    return GenerationResult.model_validate(
        {
            "review_id": TARGET.review_id,
            "course_id": TARGET.course_id,
            "source_commit": "abc123",
            "generated_by": "claude-opus-5",
            "prompt_version": "2026-07-30.1",
            "items": [
                {
                    "difficulty": 3,
                    "reason": "語彙",
                    "item": {
                        "kind": "vocab",
                        "sub_skill": "recall",
                        "word": "presided",
                        "meaning": "主宰した",
                        "example": "She presided over the meeting.",
                    },
                },
                {
                    "difficulty": 2,
                    "reason": "読解",
                    "item": {
                        "kind": "reading",
                        "passage": "A linked list stores each element in a node.",
                        "question": "Where is each element stored?",
                        "choices": ["In a node.", "In an array slot."],
                        "answer_index": 0,
                        "explanation": "The passage says each element lives in a node.",
                    },
                },
                {
                    "difficulty": 3,
                    "reason": "文法",
                    "item": {
                        "kind": "grammar",
                        "sentence": "The report was submitted ____ before the deadline.",
                        "choices": ["punctual", "punctually", "punctuality", "punctualize"],
                        "answer_index": 1,
                        "explanation": "動詞を修飾するには副詞が必要。",
                        "point": "副詞の用法",
                        "pattern": "A",
                        "pattern_note": "同じ語の別の形",
                    },
                },
            ],
        }
    )


def _other_result() -> GenerationResult:
    return GenerationResult.model_validate(
        {
            "review_id": OTHER_TARGET.review_id,
            "course_id": OTHER_TARGET.course_id,
            "source_commit": "abc123",
            "generated_by": "claude-opus-5",
            "prompt_version": "2026-07-30.1",
            "items": [
                {
                    "difficulty": 3,
                    "reason": "章の中心概念",
                    "item": {
                        "kind": "vocab",
                        "sub_skill": "recall",
                        "word": "linked list",
                        "meaning": "線形リスト",
                        "example": "A linked list stores each element in a node.",
                    },
                }
            ],
        }
    )


@pytest.fixture
def db(tmp_path):
    connection = connect(tmp_path / "english.db")
    generate.upsert_material(connection, TARGET)
    generate.upsert_material(connection, OTHER_TARGET)
    yield connection
    connection.close()


def test_dashboard_is_empty_but_valid_before_any_study(db):
    generate.ingest(db, _result())
    result = dashboard.build_dashboard(db, "english")

    assert result["course_id"] == "english"
    assert result["mastery_by_domain"] == []
    assert result["weakest_domain"] is None
    assert len(result["due_counts"]) == 3  # vocab/reading/grammar とも未出題ぶんが due
    assert len(result["trend"]) == 14
    assert result["streak_days"] == 0
    assert result["error_causes"] == []
    assert result["open_candidates"] == 0
    # まだ mastery データが無いのでTOEIC目安も出さない
    assert result["toeic_reading_estimate"] is None


def test_studying_populates_mastery_streak_and_todays_trend(db):
    vocab_id, reading_id, grammar_id = generate.ingest(db, _result())
    session_id = study.start_session(db, "english")

    study.answer(db, session_id, vocab_id, "presided", elapsed_ms=1_000, self_confidence=1.0)
    study.answer(db, session_id, reading_id, "0", elapsed_ms=2_000, self_confidence=1.0)
    study.answer(db, session_id, grammar_id, "1", elapsed_ms=3_000, self_confidence=1.0)

    result = dashboard.build_dashboard(db, "english")

    domains = {row["domain"] for row in result["mastery_by_domain"]}
    assert domains == {"vocabulary", "reading", "grammar"}
    assert all(row["mastery"] > 0 for row in result["mastery_by_domain"])
    assert result["streak_days"] == 1
    assert result["trend"][-1]["attempts"] == 3
    assert result["trend"][-1]["correct"] == 3
    # 全問正解した直後でも過去分（13日ぶん）は0のまま
    assert all(day["attempts"] == 0 for day in result["trend"][:-1])
    # 全問正解している以上、目安スコアは最低点(5)より高い
    assert result["toeic_reading_estimate"]["score"] > 5


def test_weakest_domain_is_the_one_with_lowest_mastery(db):
    vocab_id, reading_id, grammar_id = generate.ingest(db, _result())
    session_id = study.start_session(db, "english")

    # vocab は正解、grammar は不正解を繰り返して mastery を引き離す。
    for _ in range(3):
        study.answer(db, session_id, vocab_id, "presided", elapsed_ms=1_000, self_confidence=1.0)
        study.answer(db, session_id, grammar_id, "0", elapsed_ms=1_000)  # 不正解(正解は index 1)

    result = dashboard.build_dashboard(db, "english")
    assert result["weakest_domain"] == "grammar"


def test_repeated_failures_show_up_as_error_causes_and_open_candidates(db):
    vocab_id, _, _ = generate.ingest(db, _result())
    session_id = study.start_session(db, "english")
    for _ in range(3):
        study.answer(db, session_id, vocab_id, "wrong answer", elapsed_ms=4_000)

    result = dashboard.build_dashboard(db, "english")

    assert result["open_candidates"] == 1
    causes = {row["cause"] for row in result["error_causes"]}
    assert "material_gap" in causes


def test_other_courses_do_not_leak_into_the_english_dashboard(db):
    vocab_id, _, _ = generate.ingest(db, _result())
    other_vocab_id, = generate.ingest(db, _other_result())
    session_id = study.start_session(db, "english")
    other_session_id = study.start_session(db, "dsa")

    study.answer(db, session_id, vocab_id, "presided", elapsed_ms=1_000, self_confidence=1.0)
    study.answer(db, other_session_id, other_vocab_id, "linked list", elapsed_ms=1_000, self_confidence=1.0)

    english = dashboard.build_dashboard(db, "english")
    dsa = dashboard.build_dashboard(db, "dsa")

    assert english["trend"][-1]["attempts"] == 1
    assert dsa["trend"][-1]["attempts"] == 1
    # dsa は course_id != "english" なのでTOEIC目安を出さない
    assert dsa["toeic_reading_estimate"] is None
