"""render_md() が render_tex() と同じ「答えを設問セクションに漏らさない」構成を守ることを固定する。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from acenglish.items import GrammarItem  # noqa: E402
from toeic_reading.render import render_md  # noqa: E402


def _item() -> GrammarItem:
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


def test_the_question_section_does_not_leak_the_answer():
    md = render_md("Part5 テスト", [_item()])
    questions, _, answers = md.partition("## 解答と解説")

    assert "punctually" in questions  # 選択肢としては出てよい
    assert "副詞の用法" not in questions
    assert "動詞を修飾するには副詞が必要" not in questions
    assert "副詞の用法" in answers
    assert "動詞を修飾するには副詞が必要" in answers


def test_the_correct_choice_label_is_shown_in_the_answer_section():
    md = render_md("Part5 テスト", [_item()])
    _, _, answers = md.partition("## 解答と解説")

    assert "正解: B" in answers  # answer_index=1 → (B)


def test_the_pattern_legend_is_included():
    md = render_md("Part5 テスト", [_item()])

    assert "パターンについて" in md
    assert "パターンA" in md
    assert "パターンB" in md
    assert "パターンC" in md


def test_choices_are_listed_with_letter_labels():
    md = render_md("Part5 テスト", [_item()])
    questions, _, _ = md.partition("## 解答と解説")

    assert "(A) punctual" in questions
    assert "(B) punctually" in questions
    assert "(C) punctuality" in questions
    assert "(D) punctualize" in questions
