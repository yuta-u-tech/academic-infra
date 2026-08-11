"""間違えたTOEIC問題からFrameScript用のスライド配列を組み立てる（review_slides.py）。"""

import json

import pytest

from academic_audio.engines import WavEngine
from academic_audio.review_slides import ReviewSlideError, build_slides

ROW = {
    "review_id": "toeic.part5.20260810.0005",
    "payload": json.dumps(
        {
            "kind": "grammar",
            "sentence": "The new policy applies to all staff ____ of their department.",
            "choices": ["regardless", "despite", "in spite", "notwithstanding"],
            "answer_index": 0,
            "explanation": "正解はregardlessです。despiteは不可です。in spiteも不可です。",
        }
    ),
}

CONTENT = {
    "toeic.part5.20260810.0005": {
        "reason_en": "Regardless of means no matter what. Despite cannot take of again.",
        "points": [{"label": "A", "text": "regardless of fits naturally."}],
        "question_ja": "問題1。新しい方針は部署に関係なく適用されます。",
        "choices_ja": "選択肢: A regardless / B despite / C in spite / D notwithstanding",
    }
}


@pytest.fixture
def audio_dir(tmp_path):
    return tmp_path / "audio"


def test_a_wrong_item_becomes_two_slides(audio_dir):
    slides = build_slides([ROW], CONTENT, audio_dir, WavEngine())
    assert len(slides) == 2
    assert slides[0]["kind"] == "question"
    assert slides[1]["kind"] == "answer"


def test_the_question_slide_carries_the_choices_and_audio(audio_dir):
    slides = build_slides([ROW], CONTENT, audio_dir, WavEngine())
    question = slides[0]
    assert question["choices"] == ["regardless", "despite", "in spite", "notwithstanding"]
    assert question["reviewId"] == "toeic.part5.20260810.0005"
    assert (audio_dir / "toeic.part5.20260810.0005.slide1.wav").exists()
    assert question["durationSeconds"] > 0


def test_the_answer_slide_carries_points_and_example(audio_dir):
    slides = build_slides([ROW], CONTENT, audio_dir, WavEngine())
    answer = slides[1]
    assert answer["answerLabel"] == "A"
    assert answer["answerWord"] == "regardless"
    assert answer["points"] == CONTENT[ROW["review_id"]]["points"]
    assert (audio_dir / "toeic.part5.20260810.0005.slide2.wav").exists()


def test_japanese_captions_reuse_the_db_explanation_not_authored_text(audio_dir):
    """JA字幕はDBのexplanationをそのまま使う。二重に書かせない。"""
    slides = build_slides([ROW], CONTENT, audio_dir, WavEngine())
    answer = slides[1]
    ja_text = "".join(cue["text"] for cue in answer["captionsJa"])
    assert "regardlessです" in ja_text


def test_captions_do_not_overlap_in_time(audio_dir):
    slides = build_slides([ROW], CONTENT, audio_dir, WavEngine())
    for slide in slides:
        for cues in (slide["captionsEn"], slide["captionsJa"]):
            for a, b in zip(cues, cues[1:]):
                assert a["end"] <= b["start"] + 1e-6


def test_missing_authored_content_is_rejected(audio_dir):
    with pytest.raises(ReviewSlideError, match="toeic.part5.20260810.0005"):
        build_slides([ROW], {}, audio_dir, WavEngine())


def test_missing_required_field_is_rejected(audio_dir):
    broken = {ROW["review_id"]: {k: v for k, v in CONTENT[ROW["review_id"]].items() if k != "reason_en"}}
    with pytest.raises(ReviewSlideError, match="reason_en"):
        build_slides([ROW], broken, audio_dir, WavEngine())


def test_question_numbers_are_sequential_across_items(audio_dir):
    row2 = {**ROW, "review_id": "toeic.part5.20260810.0009"}
    content2 = {**CONTENT, "toeic.part5.20260810.0009": CONTENT[ROW["review_id"]]}
    slides = build_slides([ROW, row2], content2, audio_dir, WavEngine())
    assert slides[0]["index"] == 1
    assert slides[2]["index"] == 2
