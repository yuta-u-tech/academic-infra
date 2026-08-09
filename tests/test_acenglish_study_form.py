"""Google Forms 経由（選択式）の回答記録（study.record_form_response）。

翌朝バッチはローカルUI(acenglish serve)のセッションを持たないので、
answer() が前提にする item_id ではなく review_id だけで呼べる必要がある。
"""

import pytest

from acenglish.db import connect
from acenglish.fetch import import_toeic_part5
from acenglish.items import GrammarItem
from acenglish import study

ITEM = GrammarItem.model_validate(
    {
        "sentence": "The manager ____ the report yesterday.",
        "choices": ["submit", "submits", "submitted", "submitting"],
        "answer_index": 2,
        "explanation": "過去の出来事なので過去形。",
        "point": "時制",
        "pattern": "A",
        "pattern_note": "同じ語(submit)の語形違いのみで構成しているため。",
    }
)


@pytest.fixture
def db(tmp_path):
    connection = connect(tmp_path / "english.db")
    import_toeic_part5(connection, "20260809", [ITEM])
    yield connection
    connection.close()


def _review_id(db) -> str:
    row = db.execute("SELECT review_id FROM generated_item WHERE kind = 'grammar' LIMIT 1").fetchone()
    return row["review_id"]


def test_find_item_id_by_review_id_resolves_a_toeic_item(db):
    review_id = _review_id(db)
    item_id = study.find_item_id_by_review_id(db, review_id)

    row = db.execute("SELECT id FROM generated_item WHERE review_id = ?", (review_id,)).fetchone()
    assert item_id == row["id"]


def test_find_item_id_by_review_id_returns_none_for_unknown_review_id(db):
    assert study.find_item_id_by_review_id(db, "toeic.part5.nope.9999") is None


def test_record_form_response_scores_a_correct_choice_answer(db):
    review_id = _review_id(db)
    session_id = study.start_session(db, "toeic")

    outcome = study.record_form_response(db, session_id, review_id, "2")  # index of "submitted"

    assert outcome.correct is True


def test_record_form_response_scores_an_incorrect_choice_answer(db):
    review_id = _review_id(db)
    session_id = study.start_session(db, "toeic")

    outcome = study.record_form_response(db, session_id, review_id, "0")  # "submit"

    assert outcome.correct is False


def test_record_form_response_raises_for_unknown_review_id(db):
    session_id = study.start_session(db, "toeic")

    with pytest.raises(LookupError):
        study.record_form_response(db, session_id, "toeic.part5.nope.9999", "0")
