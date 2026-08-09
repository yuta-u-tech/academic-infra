"""toeic_forms.reflect.extract_answers（Forms API回答→english.db記録用データ変換、ネットワーク無し）。"""

import pytest

from toeic_forms.reflect import ReflectError, extract_answers

FORM_MAP_ITEMS = {
    "toeic.listening.part2.20260809.0001": {
        "question_item_id": "q1",
        "choices": ["9 AM", "10 AM", "11 AM"],
    },
    "toeic.listening.part2.20260809.0002": {
        "question_item_id": "q2",
        "choices": ["A", "B", "C"],
    },
}


def _response(response_id: str, answers: dict) -> dict:
    return {"responseId": response_id, "answers": answers}


def _text_answer(item_id: str, value: str) -> dict:
    return {item_id: {"textAnswers": {"answers": [{"value": value}]}}}


def test_extract_answers_converts_choice_text_to_index():
    responses = [_response("r1", _text_answer("q1", "10 AM"))]

    result = extract_answers(FORM_MAP_ITEMS, responses)

    assert result == [
        {"review_id": "toeic.listening.part2.20260809.0001", "response": "1", "response_id": "r1"}
    ]


def test_extract_answers_skips_unanswered_questions():
    responses = [_response("r1", _text_answer("q1", "10 AM"))]

    result = extract_answers(FORM_MAP_ITEMS, responses)

    review_ids = {row["review_id"] for row in result}
    assert "toeic.listening.part2.20260809.0002" not in review_ids


def test_extract_answers_keeps_the_last_submission_for_a_repeated_review_id():
    responses = [
        _response("r1", _text_answer("q1", "9 AM")),
        _response("r2", _text_answer("q1", "10 AM")),
    ]

    result = extract_answers(FORM_MAP_ITEMS, responses)

    assert len(result) == 1
    assert result[0]["response"] == "1"
    assert result[0]["response_id"] == "r2"


def test_extract_answers_raises_when_value_is_not_in_choices():
    responses = [_response("r1", _text_answer("q1", "noon"))]

    with pytest.raises(ReflectError):
        extract_answers(FORM_MAP_ITEMS, responses)


def test_extract_answers_returns_empty_list_for_no_responses():
    assert extract_answers(FORM_MAP_ITEMS, []) == []
