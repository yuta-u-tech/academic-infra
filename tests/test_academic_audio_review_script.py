"""間違えたTOEIC問題のJSON(reason付き)から復習動画の台本を組み立てる（review_script.py）。"""

import pytest

from academic_audio.review_script import ReviewItemError, build_review_script

ITEM = {
    "review_id": "toeic.part5.20260810.0005",
    "sentence": "The new policy applies to all staff ____ of their department.",
    "choices": ["regardless", "despite", "in spite", "notwithstanding"],
    "answer_index": 0,
    "reason": "Regardless of means no matter what; despite and notwithstanding already act like of.",
}


def test_a_question_becomes_four_segments_plus_intro_outro():
    script = build_review_script("TOEIC Review", "toeic.review.20260810", [ITEM])
    assert len(script.segments) == 4 + 2  # intro/outro + question/choices/answer/reason
    assert script.segments[0].id == "intro"
    assert script.segments[-1].id == "outro"


def test_the_blank_is_spoken_not_printed_as_underscores():
    script = build_review_script("TOEIC Review", "toeic.review.20260810", [ITEM])
    question = next(s for s in script.segments if s.role == "question")
    assert "____" not in question.text
    assert "blank" in question.text


def test_choices_are_lettered():
    script = build_review_script("TOEIC Review", "toeic.review.20260810", [ITEM])
    choices = next(s for s in script.segments if s.role == "choices")
    assert choices.text == "A, regardless. B, despite. C, in spite. D, notwithstanding."


def test_the_answer_names_the_correct_letter_and_word():
    script = build_review_script("TOEIC Review", "toeic.review.20260810", [ITEM])
    answer = next(s for s in script.segments if s.role == "answer")
    assert answer.text == "The answer is A, regardless."


def test_segments_share_the_review_id_as_item_id():
    script = build_review_script("TOEIC Review", "toeic.review.20260810", [ITEM])
    per_item = [s for s in script.segments if s.item_id == ITEM["review_id"]]
    assert len(per_item) == 4


def test_no_items_is_rejected():
    with pytest.raises(ReviewItemError):
        build_review_script("TOEIC Review", "toeic.review.20260810", [])


def test_a_missing_field_is_rejected():
    broken = {k: v for k, v in ITEM.items() if k != "reason"}
    with pytest.raises(ReviewItemError, match="reason"):
        build_review_script("TOEIC Review", "toeic.review.20260810", [broken])


def test_an_out_of_range_answer_index_is_rejected():
    broken = {**ITEM, "answer_index": 9}
    with pytest.raises(ReviewItemError, match="answer_index"):
        build_review_script("TOEIC Review", "toeic.review.20260810", [broken])
