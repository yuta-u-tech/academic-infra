"""間違えたTOEICリスニング問題からFrameScript用のスライド配列を組み立てる。

Part5用(review_slides.py)とは別テンプレート — 会話台本の再現とシャドーイングが
要る点が違うので、器も分ける。Passage(会話/スピーチの通し聴き) → 1問=質問1枚+
解説1枚(Q1/A1/Q2/A2/...) → 発音1枚 → シャドーイング1枚(2026-08-12: 全設問を
1枚に乗せると字幕と重なるほど密度過多という指摘を受けて、Part5と同じ1問=1枚方式に
変更。さらに「設問の前提となる会話が1枚目にあってもいい」という指摘を受けて
Passageスライドを追加)。字幕は文単位に分割し、選択肢は音声のみ・字幕には出さない
(2026-08-12「字幕が大きくなりすぎている」の指摘への対応)。発音スライドは
「該当する時だけ」ではなく毎回出す、という明示の指示への対応。フレーズの発音
ポイントは例文つきで示す(2026-08-12「例文で実際にどう発音されるか」の指摘)。
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
            "explanation": "冒頭で「間違ったラベルが貼られていた」と述べている。二つ目の文はここ。",
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
            "The speakers open by pointing out wrong labels on boxes. That is the problem.",
            "Words like packing area and shipping records place this at a shipping facility.",
        ],
        "question_ja": [
            "話者が話し合っている問題は何ですか。",
            "この会話はどこで行われていますか。",
        ],
        "points": [
            [
                {"label": "A", "text": "Wrong labels were printed, matching the opening line directly."},
                {"label": "B", "text": "Printer trouble is mentioned, but the fault was an old template, not a breakdown."},
            ],
            [
                {"label": "C", "text": "Packing area and shipping records point to a shipping facility."},
                {"label": "A", "text": "Printer wording is a sound-alike distractor, not a print shop."},
            ],
        ],
        "pronunciation_intro_en": "Notice how these phrases link together in fast speech.",
        "pronunciation_intro_ja": "これらのフレーズがつながる様子に注目しましょう。",
        "pronunciation_points": [
            {
                "phrase": "went out",
                "note_en": "went out links into one sound, like wen-tout.",
                "note_ja": "went out は t が次の母音とつながり「ウェンタウト」のように聞こえます。",
                "example_en": "The shipment went out yesterday afternoon.",
            },
        ],
    }
}


@pytest.fixture
def audio_dir(tmp_path):
    return tmp_path / "audio"


def test_a_two_question_passage_becomes_seven_slides(audio_dir):
    """Passage/Q1/A1/Q2/A2/発音/シャドーイング = 7枚。"""
    slides = build_slides_listening([PASSAGE], CONTENT, audio_dir, WavEngine())
    assert [s["kind"] for s in slides] == [
        "passage", "question", "explanation", "question", "explanation", "pronunciation", "shadowing",
    ]


def test_the_passage_slide_plays_the_full_conversation_before_any_question(audio_dir):
    """2026-08-12「設問の前提となる会話が1枚目にあってもいい」の指摘への対応。"""
    slides = build_slides_listening([PASSAGE], CONTENT, audio_dir, WavEngine())
    passage_slide = slides[0]
    assert passage_slide["introEn"] == PASSAGE["introEn"]
    assert passage_slide["transcript"] == PASSAGE["transcript"]
    assert passage_slide["captionsEn"][0]["text"] == PASSAGE["introEn"]
    assert (audio_dir / f"{PASSAGE['passageId']}.passage.wav").exists()


def test_each_question_slide_carries_exactly_one_question(audio_dir):
    slides = build_slides_listening([PASSAGE], CONTENT, audio_dir, WavEngine())
    q1, q2 = slides[1], slides[3]
    assert q1["questionNumber"] == 1
    assert q1["totalQuestions"] == 2
    assert q1["choices"] == ["Incorrect labels were printed.", "A printer broke down.", "Boxes were damaged.", "A shipment was late."]
    assert q1["reviewId"] == "toeic.listening.part3.20260809.0001.1"
    assert q2["questionNumber"] == 2
    assert (audio_dir / f"{PASSAGE['passageId']}.q1.wav").exists()
    assert (audio_dir / f"{PASSAGE['passageId']}.q2.wav").exists()


def test_the_intro_line_is_only_spoken_once_on_the_first_question(audio_dir):
    slides = build_slides_listening([PASSAGE], CONTENT, audio_dir, WavEngine())
    q1, q2 = slides[1], slides[3]
    assert q1["captionsEn"][0]["text"] == PASSAGE["introEn"]
    assert all(cue["text"] != PASSAGE["introEn"] for cue in q2["captionsEn"])


def test_the_question_slide_captions_the_question_but_not_the_choices(audio_dir):
    """選択肢は画面のカードで既に読めるので、字幕には出さない(はみ出し防止)。"""
    slides = build_slides_listening([PASSAGE], CONTENT, audio_dir, WavEngine())
    q1 = slides[1]
    all_caption_text = " ".join(cue["text"] for cue in q1["captionsEn"] + q1["captionsJa"])
    assert "Number 1." in all_caption_text
    assert "Incorrect labels were printed" not in all_caption_text
    assert q1["captionsJa"][-1]["text"] == "話者が話し合っている問題は何ですか。"


def test_each_explanation_slide_reveals_its_own_answer(audio_dir):
    slides = build_slides_listening([PASSAGE], CONTENT, audio_dir, WavEngine())
    a1, a2 = slides[2], slides[4]
    assert a1["answerLabel"] == "A"
    assert a2["answerLabel"] == "C"


def test_each_explanation_slide_carries_its_own_structured_points(audio_dir):
    """答えの文字だけでは粒度が低いという指摘(2026-08-12)への対応。"""
    slides = build_slides_listening([PASSAGE], CONTENT, audio_dir, WavEngine())
    a1, a2 = slides[2], slides[4]
    assert a1["points"] == CONTENT[PASSAGE["passageId"]]["points"][0]
    assert a2["points"] == CONTENT[PASSAGE["passageId"]]["points"][1]


def test_explanation_captions_are_split_into_short_sentence_cues_not_one_giant_block(audio_dir):
    """2026-08-12「字幕が大きくなりすぎている」の指摘への対応。"""
    slides = build_slides_listening([PASSAGE], CONTENT, audio_dir, WavEngine())
    a1 = slides[2]
    assert len(a1["captionsEn"]) >= 2
    assert len(a1["captionsJa"]) >= 2
    for cue in a1["captionsEn"] + a1["captionsJa"]:
        assert len(cue["text"]) < 60
    joined_ja = "".join(cue["text"] for cue in a1["captionsJa"])
    assert "間違ったラベル" in joined_ja


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


def test_pronunciation_points_are_narrated_with_their_example_sentence(audio_dir):
    """発音ポイントはフレーズの説明だけでなく、例文でどう発音されるかも音声つきで
    示してほしいという指摘(2026-08-12)への対応。"""
    slides = build_slides_listening([PASSAGE], CONTENT, audio_dir, WavEngine())
    pronunciation = next(s for s in slides if s["kind"] == "pronunciation")
    joined_en = " ".join(cue["text"] for cue in pronunciation["captionsEn"])
    assert "The shipment went out yesterday afternoon." in joined_en


def test_the_shadowing_slide_replays_the_original_transcript_verbatim(audio_dir):
    slides = build_slides_listening([PASSAGE], CONTENT, audio_dir, WavEngine())
    shadowing = slides[-1]
    assert shadowing["kind"] == "shadowing"
    assert shadowing["transcript"] == PASSAGE["transcript"]
    assert (audio_dir / f"{PASSAGE['passageId']}.shadowing.wav").exists()


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


def test_question_ja_count_must_match_question_count(audio_dir):
    broken = {PASSAGE["passageId"]: {**CONTENT[PASSAGE["passageId"]], "question_ja": ["only one"]}}
    with pytest.raises(ReviewSlideError, match="question_ja"):
        build_slides_listening([PASSAGE], broken, audio_dir, WavEngine())


def test_points_count_must_match_question_count(audio_dir):
    broken = {PASSAGE["passageId"]: {**CONTENT[PASSAGE["passageId"]], "points": [[{"label": "A", "text": "x"}]]}}
    with pytest.raises(ReviewSlideError, match="points"):
        build_slides_listening([PASSAGE], broken, audio_dir, WavEngine())


def test_passage_numbers_are_sequential_across_passages(audio_dir):
    passage2 = {**PASSAGE, "passageId": "toeic.listening.part3.20260809.0002"}
    content2 = {**CONTENT, "toeic.listening.part3.20260809.0002": CONTENT[PASSAGE["passageId"]]}
    slides = build_slides_listening([PASSAGE, passage2], content2, audio_dir, WavEngine())
    assert slides[0]["index"] == 1
    assert slides[7]["index"] == 2
