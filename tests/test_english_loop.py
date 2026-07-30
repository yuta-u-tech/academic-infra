"""MVP の閉ループを一本通す（要件 §14）。

    資料選択 → 生成物の取り込み → 学習 → 回答記録 → 誤答原因 → 学習者モデル更新
        → 復習キュー → 追記候補 → findings.json（既存の Issue 昇華経路の入力）
"""

import json

import pytest

from acenglish import generate, promote, study
from acenglish.db import connect
from acenglish.items import GenerationResult
from acenglish.target import LearningTarget

TARGET = LearningTarget(
    review_id="dsa.ch02.list.s01",
    course_id="dsa",
    title="線形リスト",
    chapter_title="リスト構造",
    source_file="src/chapters/ch02.tex",
    section_file="sections/ch02-01.md",
    source_commit="abc123",
    body="# 線形リスト\n\n先頭から順にたどる。",
)


def _result(commit: str = "abc123") -> GenerationResult:
    return GenerationResult.model_validate(
        {
            "review_id": TARGET.review_id,
            "course_id": TARGET.course_id,
            "source_commit": commit,
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
                },
                {
                    "difficulty": 2,
                    "reason": "定義文の読解",
                    "item": {
                        "kind": "reading",
                        "passage": "A linked list stores each element in a node.",
                        "question": "Where is each element stored?",
                        "choices": ["In a node.", "In an array slot."],
                        "answer_index": 0,
                        "explanation": "The passage says each element lives in a node.",
                    },
                },
            ],
        }
    )


@pytest.fixture
def db(tmp_path):
    connection = connect(tmp_path / "english.db")
    generate.upsert_material(connection, TARGET)
    yield connection
    connection.close()


def test_generation_request_carries_material_and_provenance():
    request = generate.request(TARGET, ["vocab", "reading"], count=3)
    assert request["material"] == TARGET.body
    assert request["target"]["source_commit"] == "abc123"
    assert request["count_per_kind"] == 3


def test_unknown_kinds_are_rejected_before_asking_for_generation():
    with pytest.raises(generate.UnknownKindError, match="listening"):
        generate.request(TARGET, ["listening"])


def test_ingested_items_keep_where_they_came_from(db):
    item_ids = generate.ingest(db, _result())
    row = db.execute("SELECT * FROM generated_item WHERE id = ?", (item_ids[0],)).fetchone()
    assert row["source_commit"] == "abc123"
    assert row["reason"] == "章の中心概念"
    assert row["is_ephemeral"] == 1


def test_stale_items_retire_when_the_material_changes(db):
    generate.ingest(db, _result(commit="abc123"))
    assert generate.retire_stale(db, TARGET.review_id, "def456") == 2
    assert generate.retire_stale(db, TARGET.review_id, "def456") == 0


def test_verified_items_survive_a_material_change(db):
    """人手で確認した教材まで、資料更新を理由に勝手に消さない。"""
    item_ids = generate.ingest(db, _result())
    db.execute("UPDATE generated_item SET verified_at = '2026-07-30T00:00:00+00:00' WHERE id = ?",
               (item_ids[0],))
    db.commit()
    assert generate.retire_stale(db, TARGET.review_id, "def456") == 1


def test_the_question_shown_to_the_user_never_contains_the_answer(db):
    vocab_id, reading_id = generate.ingest(db, _result())

    vocab = study.item_for_ui(db, vocab_id)
    assert "word" not in vocab["payload"]
    assert vocab["payload"]["meaning"] == "線形リスト"

    reading = study.item_for_ui(db, reading_id)
    assert "answer_index" not in reading["payload"]
    assert "explanation" not in reading["payload"]


def test_a_correct_answer_advances_mastery_and_schedules_a_review(db):
    vocab_id, _ = generate.ingest(db, _result())
    session_id = study.start_session(db, "dsa")

    outcome = study.answer(db, session_id, vocab_id, "linked list", elapsed_ms=1_500,
                           self_confidence=1.0)

    assert outcome.correct is True
    assert outcome.error_cause is None
    assert outcome.skill_state["mastery"] > 0
    assert outcome.review["interval"] == 1
    assert outcome.revision_candidate_id is None


def test_a_slow_correct_answer_is_recorded_as_a_speed_gap(db):
    vocab_id, _ = generate.ingest(db, _result())
    session_id = study.start_session(db, "dsa")

    outcome = study.answer(db, session_id, vocab_id, "linked list", elapsed_ms=60_000)

    assert outcome.correct is True
    assert outcome.error_cause == "speed_gap"
    assert outcome.next_action == "timed_retry"


def test_repeated_failures_open_a_revision_candidate(db):
    """誤答が資料の改善材料に変わるところ。ここが要件の中心。"""
    vocab_id, _ = generate.ingest(db, _result())
    session_id = study.start_session(db, "dsa")

    outcomes = [
        study.answer(db, session_id, vocab_id, "wrong answer", elapsed_ms=4_000)
        for _ in range(3)
    ]

    assert [o.correct for o in outcomes] == [False, False, False]
    assert outcomes[0].revision_candidate_id is None
    assert outcomes[2].revision_candidate_id is not None
    assert outcomes[2].error_cause == "material_gap"
    assert outcomes[2].next_action == "revise_material"


def test_a_revision_candidate_becomes_a_findings_file(db, tmp_path):
    vocab_id, _ = generate.ingest(db, _result())
    session_id = study.start_session(db, "dsa")
    for _ in range(3):
        study.answer(db, session_id, vocab_id, "wrong answer", elapsed_ms=4_000)

    path, ids = promote.export_findings(db, tmp_path / "findings.json", "dsa")
    document = json.loads(path.read_text(encoding="utf-8"))
    finding = document["findings"][0]

    # promote_drive_comments.py が読む形（templates/review-issue.md）であること。
    assert finding["index"] == 1
    assert finding["review_id"] == TARGET.review_id
    assert finding["source_file"] == "src/chapters/ch02.tex"
    assert isinstance(finding["fix_spec"], list) and finding["fix_spec"]
    assert "3回連続" in finding["problem"]
    assert ids


def test_the_existing_issue_writer_accepts_our_findings(db, tmp_path):
    """自前で Issue 本文を組み立てず、既存スクリプトへそのまま渡せることを固定する。"""
    from promote_drive_comments import format_issue_body, load_findings, select_findings

    vocab_id, _ = generate.ingest(db, _result())
    session_id = study.start_session(db, "dsa")
    for _ in range(3):
        study.answer(db, session_id, vocab_id, "wrong answer", elapsed_ms=4_000)
    path, _ = promote.export_findings(db, tmp_path / "findings.json", "dsa")

    findings = select_findings(load_findings(path), [1])
    body = format_issue_body(findings[0], "yuta-u-tech/Data_Structure_And_Algorithms")

    assert "## 修正仕様" in body
    assert TARGET.review_id in body
    assert "src/chapters/ch02.tex" in body


def test_candidates_close_only_when_explicitly_marked(db, tmp_path):
    vocab_id, _ = generate.ingest(db, _result())
    session_id = study.start_session(db, "dsa")
    for _ in range(3):
        study.answer(db, session_id, vocab_id, "wrong answer", elapsed_ms=4_000)

    _, ids = promote.export_findings(db, tmp_path / "a.json", "dsa")
    assert promote.open_candidates(db, "dsa"), "書き出しただけでは閉じない"

    assert promote.mark_promoted(db, ids) == 1
    assert promote.open_candidates(db, "dsa") == []


def test_the_second_answer_records_the_gap_since_the_first(db):
    vocab_id, _ = generate.ingest(db, _result())
    session_id = study.start_session(db, "dsa")
    study.answer(db, session_id, vocab_id, "linked list", elapsed_ms=1_000)
    study.answer(db, session_id, vocab_id, "linked list", elapsed_ms=1_000)

    rows = db.execute("SELECT days_since_last FROM attempt ORDER BY id").fetchall()
    assert rows[0]["days_since_last"] is None
    assert rows[1]["days_since_last"] is not None
