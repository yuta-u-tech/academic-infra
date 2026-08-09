"""toeic_reading.render の form_url 埋め込み（Part5/Part7共通）。"""

from acenglish.items import GrammarItem
from acenglish.sources.toeic_part7 import Part7Passage
from toeic_reading.render import render_reading_tex, render_tex

_FORM_URL = "https://docs.google.com/forms/d/e/xyz/viewform"


def _grammar_item() -> GrammarItem:
    return GrammarItem.model_validate(
        {
            "sentence": "The report was submitted ____ before the deadline.",
            "choices": ["punctual", "punctually", "punctuality", "punctualize"],
            "answer_index": 1,
            "explanation": "動詞を修飾するには副詞が必要なのでpunctually。",
            "point": "副詞の用法",
            "pattern": "A",
            "pattern_note": "同じ語の別の形のみで構成しているため。",
        }
    )


def _passage() -> Part7Passage:
    return Part7Passage.model_validate(
        {
            "passage": "Dear Team, the meeting has been moved to 3 PM.",
            "passage_type": "single",
            "questions": [
                {
                    "question": "What time is the meeting now?",
                    "choices": ["1 PM", "2 PM", "3 PM", "4 PM"],
                    "answer_index": 2,
                    "explanation": "本文に3 PMと明記されている。",
                    "sub_skill": "comprehension",
                }
            ],
        }
    )


def test_part5_worksheet_includes_the_form_url_when_given():
    tex = render_tex("Part5 テスト", [_grammar_item()], form_url=_FORM_URL)

    assert r"\href{" + _FORM_URL + r"}{回答フォームはこちら}" in tex


def test_part5_worksheet_omits_the_form_line_when_no_url():
    tex = render_tex("Part5 テスト", [_grammar_item()])

    assert "回答フォーム" not in tex


def test_part7_worksheet_includes_the_form_url_when_given():
    tex = render_reading_tex("Part7 テスト", [_passage()], form_url=_FORM_URL)

    assert r"\href{" + _FORM_URL + r"}{回答フォームはこちら}" in tex


def test_part7_worksheet_omits_the_form_line_when_no_url():
    tex = render_reading_tex("Part7 テスト", [_passage()])

    assert "回答フォーム" not in tex
