"""間違えたTOEIC Part2(会話なし、発言+応答3つ)のスライド配列を組み立てる。

Part3/4(review_slides_listening.py)は1パッセージ=4枚(質問/解説/発音/シャドーイング)
だが、Part2には共有パッセージが無いので3枚(質問/解説/発音)に留める、と
2026-08-12に合意した内容への対応。シャドーイング枚は無し。字幕は文単位に分割し、
選択肢は音声のみ・字幕には出さない(2026-08-12「字幕が大きくなりすぎている」の
指摘への対応)。
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
    "explanation": "正解は(A)。Whenで時期を聞いているので曜日と時間帯で答える(A)が適切。他の選択肢は疑問詞や音の取り違え。",
}

CONTENT = {
    "toeic.listening.part2.20260809.0001": {
        "reason_en": "The question asks When. The reply must give a day and a time.",
        "question_ja": "部署会議はいつに変更されましたか。",
        "points": [
            {"label": "A", "text": "Gives a day and a time, matching the When question directly."},
            {"label": "B", "text": "Answers a Where question, a common When/Where mix-up trap."},
        ],
        "pronunciation_intro_en": "Notice how these phrases link together in fast speech.",
        "pronunciation_intro_ja": "これらのフレーズがつながる様子に注目しましょう。",
        "pronunciation_points": [
            {
                "phrase": "moved to",
                "note_en": "moved to links into one sound, like moove-tuh.",
                "note_ja": "moved to は d が次の母音とつながります。",
                "example_en": "The meeting was moved to Thursday.",
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


def test_the_question_slide_carries_the_choices_but_does_not_caption_them(audio_dir):
    slides = build_slides_listening_part2([ITEM], CONTENT, audio_dir, WavEngine())
    question = slides[0]
    assert question["reviewId"] == ITEM["reviewId"]
    assert question["choices"] == ITEM["choices"]
    assert (audio_dir / f"{ITEM['reviewId']}.slide1.wav").exists()
    all_caption_text = " ".join(cue["text"] for cue in question["captionsEn"] + question["captionsJa"])
    assert "Thursday morning" not in all_caption_text
    assert question["captionsJa"][0]["text"] == "部署会議はいつに変更されましたか。"


def test_the_explanation_slide_reveals_the_answer_with_split_captions(audio_dir):
    slides = build_slides_listening_part2([ITEM], CONTENT, audio_dir, WavEngine())
    explanation = slides[1]
    assert explanation["answerLabel"] == "A"
    assert len(explanation["captionsJa"]) >= 2
    for cue in explanation["captionsEn"] + explanation["captionsJa"]:
        assert len(cue["text"]) < 60
    joined_ja = "".join(cue["text"] for cue in explanation["captionsJa"])
    assert "正解は(A)" in joined_ja


def test_the_explanation_slide_carries_structured_points(audio_dir):
    """答えの文字だけでは粒度が低いという指摘(2026-08-12)への対応。"""
    slides = build_slides_listening_part2([ITEM], CONTENT, audio_dir, WavEngine())
    explanation = slides[1]
    assert explanation["points"] == CONTENT[ITEM["reviewId"]]["points"]


def test_the_pronunciation_slide_is_always_present(audio_dir):
    minimal_content = {ITEM["reviewId"]: {**CONTENT[ITEM["reviewId"]], "pronunciation_points": []}}
    slides = build_slides_listening_part2([ITEM], minimal_content, audio_dir, WavEngine())
    pronunciation = [s for s in slides if s["kind"] == "pronunciation"]
    assert len(pronunciation) == 1
    assert pronunciation[0]["points"] == []


def test_pronunciation_points_are_narrated_with_their_example_sentence(audio_dir):
    """発音ポイントはフレーズの説明だけでなく、例文でどう発音されるかも音声つきで
    示してほしいという指摘(2026-08-12)への対応。"""
    slides = build_slides_listening_part2([ITEM], CONTENT, audio_dir, WavEngine())
    pronunciation = next(s for s in slides if s["kind"] == "pronunciation")
    joined_en = " ".join(cue["text"] for cue in pronunciation["captionsEn"])
    assert "The meeting was moved to Thursday." in joined_en


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
