"""スライド配列(Part2, 3種) -> FrameScriptのproject.tsx。"""

import pytest

from academic_audio.review_slides_listening_part2_tsx import render_project_tsx

QUESTION_SLIDE = {
    "kind": "question",
    "reviewId": "toeic.listening.part2.20260809.0001",
    "index": 1,
    "questionEn": "When was the meeting moved to?",
    "choices": ["A", "B", "C"],
    "soundPath": "/home/user/academic-infra/.academic-audio/jobs/x/slide1.wav",
    "durationSeconds": 10.0,
    "captionsEn": [{"start": 0, "end": 5, "text": "When was the meeting moved to?"}],
    "captionsJa": [],
}

EXPLANATION_SLIDE = {
    "kind": "explanation",
    "reviewId": "toeic.listening.part2.20260809.0001",
    "index": 1,
    "answerLabel": "A",
    "explanation": "理由はこちら。",
    "soundPath": "/home/user/academic-infra/.academic-audio/jobs/x/slide2.wav",
    "durationSeconds": 10.0,
    "captionsEn": [{"start": 0, "end": 5, "text": "The answer is A."}],
    "captionsJa": [{"start": 0, "end": 5, "text": "理由はこちら。"}],
}

PRONUNCIATION_SLIDE = {
    "kind": "pronunciation",
    "reviewId": "toeic.listening.part2.20260809.0001",
    "index": 1,
    "points": [{"phrase": "moved to", "note_en": "links together", "note_ja": "つながります"}],
    "soundPath": "/home/user/academic-infra/.academic-audio/jobs/x/slide3.wav",
    "durationSeconds": 10.0,
    "captionsEn": [{"start": 0, "end": 5, "text": "Notice."}],
    "captionsJa": [{"start": 0, "end": 5, "text": "注目。"}],
}

ALL_SLIDES = [QUESTION_SLIDE, EXPLANATION_SLIDE, PRONUNCIATION_SLIDE]


def test_no_slides_is_rejected():
    with pytest.raises(ValueError):
        render_project_tsx([], framescript_root=None)  # type: ignore[arg-type]


def test_all_three_slide_kinds_are_embedded(tmp_path):
    tsx = render_project_tsx(ALL_SLIDES, framescript_root=tmp_path)
    for kind in ("question", "explanation", "pronunciation"):
        assert f'"kind": "{kind}"' in tsx


def test_no_shadowing_type_is_defined(tmp_path):
    """Part2にはシャドーイング枚が無い(会話が無いので対象が無い)。"""
    tsx = render_project_tsx(ALL_SLIDES, framescript_root=tmp_path)
    assert "ShadowingSlide" not in tsx
    assert "ShadowingScene" not in tsx
