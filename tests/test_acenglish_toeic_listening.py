"""TOEICリスニング（Part2/3/4）の学習ループ取り込み（acenglish.fetch.import_toeic_listening*）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pytest

from academic_audio.items import load_passage_result, load_result
from acenglish.db import connect
from acenglish.fetch import import_toeic_listening, import_toeic_listening_passage


@pytest.fixture
def db(tmp_path):
    connection = connect(tmp_path / "english.db")
    yield connection
    connection.close()


def _part2_result_path(tmp_path: Path) -> Path:
    import json

    data = {
        "format": "toeic-part2",
        "title": "テスト",
        "source_id": "logic.ch01.s01",
        "source_commit": "test-commit",
        "items": [
            {
                "item_id": "item-001",
                "parts": [
                    {"role": "question", "text": "When will you finish checking the truth table?"},
                    {"role": "choice", "text": "By the end of this afternoon."},
                    {"role": "choice", "text": "In the small lecture room."},
                    {"role": "choice", "text": "The table was quite accurate."},
                ],
                "answer_index": 0,
                "explanation": "正解は (A)。When で時期を聞いている。",
                "reason": "資料の真理値表の記述に対応する。",
            }
        ],
    }
    path = tmp_path / "part2_result.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _part3_question(answer_index: int) -> dict:
    return {
        "text": "What are the two speakers mainly discussing here?",
        "choices": ["A scheduling conflict", "An unexpected test result", "A budget proposal", "A new hire"],
        "answer_index": answer_index,
        "explanation": "正解の理由をここに書く。",
    }


def _part3_result_path(tmp_path: Path) -> Path:
    import json

    data = {
        "format": "toeic-part3",
        "title": "テスト",
        "source_id": "logic.ch01.s01",
        "source_commit": "test-commit",
        "items": [
            {
                "item_id": "item-001",
                "passage": [
                    {"speaker": "A", "text": "Did you finish checking the truth table for the new circuit design?"},
                    {"speaker": "B", "text": "Almost. I found one row where the output doesn't match what we expected."},
                    {"speaker": "A", "text": "That's quite concerning, since we're presenting this design tomorrow morning."},
                    {"speaker": "B", "text": "It happens when both inputs are false. The gate outputs true instead."},
                ],
                "questions": [_part3_question(1), _part3_question(0), _part3_question(2)],
                "reason": "テスト用の会話。",
            }
        ],
    }
    path = tmp_path / "part3_result.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_import_toeic_listening_writes_generated_item(db, tmp_path):
    from academic_audio.formats import load_format

    result_path = _part2_result_path(tmp_path)
    listening_set = load_result(result_path, load_format("toeic-part2"))

    imported = import_toeic_listening(db, "20260810", listening_set, "part2")

    assert imported == 1
    row = db.execute("SELECT review_id, kind FROM generated_item WHERE kind = 'listening'").fetchone()
    assert row["review_id"] == "toeic.listening.part2.20260810.0001"


def test_import_toeic_listening_is_idempotent(db, tmp_path):
    from academic_audio.formats import load_format

    result_path = _part2_result_path(tmp_path)
    listening_set = load_result(result_path, load_format("toeic-part2"))

    first = import_toeic_listening(db, "20260810", listening_set, "part2")
    second = import_toeic_listening(db, "20260810", listening_set, "part2")

    assert first == 1
    assert second == 0


def test_import_toeic_listening_passage_creates_one_review_id_per_question(db, tmp_path):
    from academic_audio.formats import load_format

    result_path = _part3_result_path(tmp_path)
    passage_set = load_passage_result(result_path, load_format("toeic-part3"))

    imported = import_toeic_listening_passage(db, "20260810", passage_set, "part3")

    assert imported == 3
    review_ids = {
        row["review_id"]
        for row in db.execute("SELECT review_id FROM generated_item WHERE kind = 'listening'").fetchall()
    }
    assert review_ids == {
        "toeic.listening.part3.20260810.0001.1",
        "toeic.listening.part3.20260810.0001.2",
        "toeic.listening.part3.20260810.0001.3",
    }


def test_record_form_response_works_for_listening_items(db, tmp_path):
    """toeic_forms経由の record が listening にもそのまま使えることを確認する
    （kind非依存に設計されているため、追加のコード変更は不要）。
    """
    from academic_audio.formats import load_format

    from acenglish import study

    result_path = _part2_result_path(tmp_path)
    listening_set = load_result(result_path, load_format("toeic-part2"))
    import_toeic_listening(db, "20260810", listening_set, "part2")

    session_id = study.start_session(db, "toeic")
    outcome = study.record_form_response(db, session_id, "toeic.listening.part2.20260810.0001", "0")

    assert outcome.correct is True
