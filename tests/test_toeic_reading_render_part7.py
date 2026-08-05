"""render_reading_md() が答えを設問セクションに漏らさず、passageを1回だけ表示することを固定する。"""

from acenglish.sources.toeic_part7 import Part7Passage
from toeic_reading.render import render_reading_md


def _passage() -> Part7Passage:
    return Part7Passage.model_validate(
        {
            "passage": "Dear Team, the meeting has been moved to 3 PM due to a scheduling conflict.",
            "passage_type": "single",
            "questions": [
                {
                    "question": "What time is the meeting now?",
                    "choices": ["1 PM", "2 PM", "3 PM", "4 PM"],
                    "answer_index": 2,
                    "explanation": "本文に3 PMと明記されている。",
                    "sub_skill": "comprehension",
                },
                {
                    "question": "Why was the meeting changed?",
                    "choices": [
                        "A holiday", "A scheduling conflict", "A power outage", "A budget issue",
                    ],
                    "answer_index": 1,
                    "explanation": "due to a scheduling conflictと明記されている。",
                    "sub_skill": "comprehension",
                },
            ],
        }
    )


def test_the_passage_appears_only_once():
    md = render_reading_md("Part7 テスト", [_passage()])

    # 本文の全文は1回だけ出る（設問ごとに繰り返し表示しない）。
    assert md.count("Dear Team, the meeting has been moved to 3 PM") == 1


def test_the_question_section_does_not_leak_the_answer():
    md = render_reading_md("Part7 テスト", [_passage()])
    questions, _, answers = md.partition("## 解答と解説")

    assert "本文に3 PMと明記されている" not in questions
    assert "本文に3 PMと明記されている" in answers


def test_questions_are_numbered_continuously_across_passages():
    md = render_reading_md("Part7 テスト", [_passage(), _passage()])
    questions, _, _ = md.partition("## 解答と解説")

    for number in (1, 2, 3, 4):
        assert f"{number}. " in questions
