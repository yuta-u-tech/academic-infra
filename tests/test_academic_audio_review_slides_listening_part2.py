"""間違えたTOEIC Part2(会話なし、発言+応答3つ)のスライド配列を組み立てる。

Part3/4(review_slides_listening.py)は1パッセージ=4枚(質問/解説/発音/シャドーイング)
だが、Part2には共有パッセージが無いので3枚(質問/解説/発音)に留める、と
2026-08-12に合意した内容への対応。シャドーイング枚は無し。
"""

import pytest

from academic_audio.engines import WavEngine
from academic_audio.review_slides_listening_part2 import (
    _SLIDE_TAIL_SECONDS,
    ReviewSlideError,
    build_slides_listening_part2,
)

ITEM = {
    "reviewId": "toeic.listening.part2.20260809.0001",
    "questionEn": "When was the department meeting moved to?",
    "choices": [
        "To Thursday morning, right after the briefing.",
        "Down the hall from the copy room.",
        "It was a business trip to the branch office.",
    ],
    "answerIndex": 0,
    "explanation": "正解は(A)。Whenで時期を聞いているので曜日と時間帯で答える(A)が適切。",
}

CONTENT = {
    "toeic.listening.part2.20260809.0001": {
        "reason_en": "The question asks When, so the reply must give a day and time.",
        "pronunciation_intro_en": "Notice how these phrases link together in fast speech.",
        "pronunciation_points": [
            {
                "phrase": "moved to",
                "note_en": "moved to links into one sound, like moove-tuh.",
                "note_ja": "moved to は d が次の母音とつながります。",
            }
        ],
    }
}


@pytest.fixture
def audio_dir(tmp_path):
    return tmp_path / "audio"


def test_an_item_becomes_three_slides(audio_dir):
    slides = build_slides_listening_part2([ITEM], CONTENT, audio_dir, WavEngine())
    assert [s["kind"] for s in slides] == ["question", "explanation", "pronunciation"]


def test_the_question_slide_carries_the_choices(audio_dir):
    slides = build_slides_listening_part2([ITEM], CONTENT, audio_dir, WavEngine())
    question = slides[0]
    assert question["reviewId"] == ITEM["reviewId"]
    assert question["choices"] == ITEM["choices"]
    assert (audio_dir / f"{ITEM['reviewId']}.slide1.wav").exists()


def test_the_explanation_slide_reveals_the_answer_and_reuses_db_explanation(audio_dir):
    slides = build_slides_listening_part2([ITEM], CONTENT, audio_dir, WavEngine())
    explanation = slides[1]
    assert explanation["answerLabel"] == "A"
    ja_text = "".join(cue["text"] for cue in explanation["captionsJa"])
    assert "正解は(A)" in ja_text


def test_the_pronunciation_slide_is_always_present(audio_dir):
    minimal_content = {ITEM["reviewId"]: {**CONTENT[ITEM["reviewId"]], "pronunciation_points": []}}
    slides = build_slides_listening_part2([ITEM], minimal_content, audio_dir, WavEngine())
    pronunciation = [s for s in slides if s["kind"] == "pronunciation"]
    assert len(pronunciation) == 1
    assert pronunciation[0]["points"] == []


def test_no_shadowing_slide_is_produced(audio_dir):
    slides = build_slides_listening_part2([ITEM], CONTENT, audio_dir, WavEngine())
    assert all(s["kind"] != "shadowing" for s in slides)


def test_a_pause_is_added_after_the_audio_ends_before_the_next_slide(audio_dir):
    slides = build_slides_listening_part2([ITEM], CONTENT, audio_dir, WavEngine())
    for slide in slides:
        last_cue_end = max(
            (cue["end"] for cues in (slide["captionsEn"], slide["captionsJa"]) for cue in cues), default=0.0
        )
        assert slide["durationSeconds"] >= last_cue_end + _SLIDE_TAIL_SECONDS - 1e-6


def test_missing_authored_content_is_rejected(audio_dir):
    with pytest.raises(ReviewSlideError, match=ITEM["reviewId"]):
        build_slides_listening_part2([ITEM], {}, audio_dir, WavEngine())


def test_missing_required_field_is_rejected(audio_dir):
    broken = {ITEM["reviewId"]: {k: v for k, v in CONTENT[ITEM["reviewId"]].items() if k != "reason_en"}}
    with pytest.raises(ReviewSlideError, match="reason_en"):
        build_slides_listening_part2([ITEM], broken, audio_dir, WavEngine())


def test_question_numbers_are_sequential_across_items(audio_dir):
    item2 = {**ITEM, "reviewId": "toeic.listening.part2.20260809.0009"}
    content2 = {**CONTENT, "toeic.listening.part2.20260809.0009": CONTENT[ITEM["reviewId"]]}
    slides = build_slides_listening_part2([ITEM, item2], content2, audio_dir, WavEngine())
    assert slides[0]["index"] == 1
    assert slides[3]["index"] == 2
