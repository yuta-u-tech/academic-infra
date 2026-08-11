"""間違えたTOEICリスニング問題からFrameScript用のスライド配列を組み立てる。

Part5用(review_slides.py)とは別テンプレート — 会話台本の再現とシャドーイングが
要る点が違うので、器も分ける。1会話(パッセージ) = 常に4枚固定
(質問/解説/発音/シャドーイング)。「該当する時だけ出す」可変枚数にはしない、と
本人が明言している(発音スライドは毎回出す)。
"""

import pytest

from academic_audio.engines import WavEngine
from academic_audio.review_slides_listening import (
    _SLIDE_TAIL_SECONDS,
    ReviewSlideError,
    build_slides_listening,
)

PASSAGE = {
    "passageId": "toeic.listening.part3.20260809.0001",
    "part": "part3",
    "introEn": "Questions 1 through 3 refer to the following conversation.",
    "transcript": [
        {"speaker": "A", "text": "The order that went out yesterday afternoon had the wrong labels."},
        {"speaker": "B", "text": "I noticed that too. The printer was pulling from an outdated file."},
    ],
    "questions": [
        {
            "reviewId": "toeic.listening.part3.20260809.0001.1",
            "question": "What problem are the speakers discussing?",
            "choices": ["Incorrect labels were printed.", "A printer broke down.", "Boxes were damaged.", "A shipment was late."],
            "answerIndex": 0,
            "explanation": "冒頭で「間違ったラベルが貼られていた」と述べている。",
        },
        {
            "reviewId": "toeic.listening.part3.20260809.0001.2",
            "question": "Where does this conversation take place?",
            "choices": ["At a print shop.", "At a design studio.", "At a shipping facility.", "At a call center."],
            "answerIndex": 2,
            "explanation": "packing area, shipping records などの語から物流拠点だと分かる。",
        },
    ],
}

CONTENT = {
    "toeic.listening.part3.20260809.0001": {
        "reason_en": [
            "The speakers open by pointing out wrong labels on boxes, so that is the problem.",
            "Words like packing area and shipping records place this at a shipping facility.",
        ],
        "pronunciation_intro_en": "Notice how these phrases link together in fast speech.",
        "pronunciation_points": [
            {"phrase": "went out", "note_en": "went out links into one sound, like wen-tout.", "note_ja": "went out は t が次の母音とつながり「ウェンタウト」のように聞こえます。"},
        ],
    }
}


@pytest.fixture
def audio_dir(tmp_path):
    return tmp_path / "audio"


def test_a_passage_becomes_four_slides(audio_dir):
    slides = build_slides_listening([PASSAGE], CONTENT, audio_dir, WavEngine())
    assert [s["kind"] for s in slides] == ["question", "explanation", "pronunciation", "shadowing"]


def test_the_question_slide_lists_every_grouped_question(audio_dir):
    slides = build_slides_listening([PASSAGE], CONTENT, audio_dir, WavEngine())
    question = slides[0]
    assert question["passageId"] == PASSAGE["passageId"]
    assert len(question["questions"]) == 2
    assert question["questions"][0]["choices"][0] == "Incorrect labels were printed."
    assert (audio_dir / f"{PASSAGE['passageId']}.slide1.wav").exists()


def test_the_explanation_slide_reveals_answers_and_reasons(audio_dir):
    slides = build_slides_listening([PASSAGE], CONTENT, audio_dir, WavEngine())
    explanation = slides[1]
    assert explanation["questions"][0]["answerLabel"] == "A"
    assert explanation["questions"][1]["answerLabel"] == "C"
    ja_text = "".join(cue["text"] for cue in explanation["captionsJa"])
    assert "間違ったラベル" in ja_text


def test_the_pronunciation_slide_is_always_present_even_without_extra_authoring(audio_dir):
    """発音スライドは条件付きにせず毎回出す、という明示の指示への対応。"""
    minimal_content = {
        PASSAGE["passageId"]: {
            **CONTENT[PASSAGE["passageId"]],
            "pronunciation_points": [],
        }
    }
    slides = build_slides_listening([PASSAGE], minimal_content, audio_dir, WavEngine())
    pronunciation = [s for s in slides if s["kind"] == "pronunciation"]
    assert len(pronunciation) == 1
    assert pronunciation[0]["points"] == []


def test_the_shadowing_slide_replays_the_original_transcript_verbatim(audio_dir):
    slides = build_slides_listening([PASSAGE], CONTENT, audio_dir, WavEngine())
    shadowing = slides[3]
    assert shadowing["transcript"] == PASSAGE["transcript"]
    assert (audio_dir / f"{PASSAGE['passageId']}.slide4.wav").exists()


def test_a_pause_is_added_after_the_audio_ends_before_the_next_slide(audio_dir):
    slides = build_slides_listening([PASSAGE], CONTENT, audio_dir, WavEngine())
    for slide in slides:
        last_cue_end = max(
            (cue["end"] for cues in (slide["captionsEn"], slide["captionsJa"]) for cue in cues), default=0.0
        )
        assert slide["durationSeconds"] >= last_cue_end + _SLIDE_TAIL_SECONDS - 1e-6


def test_missing_authored_content_is_rejected(audio_dir):
    with pytest.raises(ReviewSlideError, match=PASSAGE["passageId"]):
        build_slides_listening([PASSAGE], {}, audio_dir, WavEngine())


def test_missing_required_field_is_rejected(audio_dir):
    broken = {PASSAGE["passageId"]: {k: v for k, v in CONTENT[PASSAGE["passageId"]].items() if k != "reason_en"}}
    with pytest.raises(ReviewSlideError, match="reason_en"):
        build_slides_listening([PASSAGE], broken, audio_dir, WavEngine())


def test_reason_en_count_must_match_question_count(audio_dir):
    broken = {PASSAGE["passageId"]: {**CONTENT[PASSAGE["passageId"]], "reason_en": ["only one"]}}
    with pytest.raises(ReviewSlideError, match="reason_en"):
        build_slides_listening([PASSAGE], broken, audio_dir, WavEngine())


def test_passage_numbers_are_sequential_across_passages(audio_dir):
    passage2 = {**PASSAGE, "passageId": "toeic.listening.part3.20260809.0002"}
    content2 = {**CONTENT, "toeic.listening.part3.20260809.0002": CONTENT[PASSAGE["passageId"]]}
    slides = build_slides_listening([PASSAGE, passage2], content2, audio_dir, WavEngine())
    assert slides[0]["index"] == 1
    assert slides[4]["index"] == 2
