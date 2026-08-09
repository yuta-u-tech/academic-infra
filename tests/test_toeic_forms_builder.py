"""toeic_forms.builder のリクエスト組み立て（ネットワーク無し・純粋関数）。"""

import pytest

from toeic_forms.builder import build_choice_quiz_requests, build_free_response_requests
from toeic_forms.items import ChoiceFormItem, FreeFormItem


def _choice_item(review_id: str = "toeic.listening.part2.20260809.0001") -> ChoiceFormItem:
    return ChoiceFormItem(
        review_id=review_id,
        topic="listening",
        difficulty=3,
        question="What time does the meeting start?",
        choices=["9 AM", "10 AM", "11 AM"],
        answer_index=1,
        explanation="会話中で 10 AM と明言されている。",
    )


def _free_item(review_id: str = "toeic.listening.part2.20260809.0002") -> FreeFormItem:
    return FreeFormItem(
        review_id=review_id,
        topic="listening",
        difficulty=3,
        question="Summarize the dialogue in one sentence.",
        model_answer="The meeting was moved to 10 AM.",
        explanation="時刻変更の連絡が主旨。",
    )


def test_choice_answer_index_out_of_range_rejected():
    with pytest.raises(ValueError):
        ChoiceFormItem(
            review_id="x",
            topic="listening",
            difficulty=1,
            question="q",
            choices=["a", "b"],
            answer_index=2,
            explanation="e",
        )


def test_build_choice_quiz_requests_sets_isquiz_first():
    requests, item_map = build_choice_quiz_requests([_choice_item()])

    assert requests[0] == {
        "updateSettings": {
            "settings": {"quizSettings": {"isQuiz": True}},
            "updateMask": "quizSettings.isQuiz",
        }
    }
    assert len(requests) == 2
    assert "toeic.listening.part2.20260809.0001" in item_map


def test_build_choice_quiz_requests_grading_uses_correct_choice_value():
    item = _choice_item()
    requests, _ = build_choice_quiz_requests([item])

    create_item = requests[1]["createItem"]["item"]
    question = create_item["questionItem"]["question"]
    correct_values = [answer["value"] for answer in question["grading"]["correctAnswers"]["answers"]]

    assert correct_values == ["10 AM"]
    assert question["grading"]["whenWrong"]["text"] == item.explanation
    assert question["choiceQuestion"]["options"] == [{"value": c} for c in item.choices]


def test_build_choice_quiz_requests_item_ids_are_stable_and_unique():
    items = [_choice_item("a.1"), _choice_item("a.2")]
    requests_1, map_1 = build_choice_quiz_requests(items)
    requests_2, map_2 = build_choice_quiz_requests(items)

    assert map_1 == map_2  # 決定的（同じreview_idなら同じitemId）
    ids = [request["createItem"]["item"]["itemId"] for request in requests_1[1:]]
    assert len(ids) == len(set(ids))  # 衝突しない


def test_build_free_response_requests_has_three_sections_per_item():
    item = _free_item()
    requests, item_map = build_free_response_requests([item])

    assert len(requests) == 3
    question_item, info_item, grade_item = (request["createItem"]["item"] for request in requests)

    assert question_item["questionItem"]["question"]["textQuestion"] == {"paragraph": True}
    assert "pageBreakItem" in info_item
    assert item.model_answer in info_item["description"]
    assert item.explanation in info_item["description"]
    assert grade_item["questionItem"]["question"]["choiceQuestion"]["options"] == [
        {"value": "合っていた"},
        {"value": "部分的に合っていた"},
        {"value": "違った"},
    ]

    mapped = item_map[item.review_id]
    assert mapped["question_item_id"] == question_item["itemId"]
    assert mapped["self_grade_item_id"] == grade_item["itemId"]


def test_build_free_response_requests_multiple_items_use_sequential_locations():
    items = [_free_item("a.1"), _free_item("a.2")]
    requests, _ = build_free_response_requests(items)

    locations = [request["createItem"]["location"]["index"] for request in requests]
    assert locations == [0, 1, 2, 3, 4, 5]
