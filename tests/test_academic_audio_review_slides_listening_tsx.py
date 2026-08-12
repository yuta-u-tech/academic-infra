"""スライド配列(Part3/4, 4種、1問=1枚) -> FrameScriptのproject.tsx。"""

import pytest

from academic_audio.review_slides_listening_tsx import render_project_tsx

QUESTION_SLIDE = {
    "kind": "question",
    "passageId": "toeic.listening.part3.20260809.0001",
    "index": 1,
    "questionNumber": 1,
    "totalQuestions": 2,
    "question": "What problem?",
    "choices": ["A", "B", "C", "D"],
    "reviewId": "x.1",
    "soundPath": "/home/user/academic-infra/.academic-audio/jobs/x/q1.wav",
    "durationSeconds": 10.0,
    "captionsEn": [{"start": 0, "end": 5, "text": "Number 1."}],
    "captionsJa": [{"start": 0, "end": 5, "text": "1問目。"}],
}

EXPLANATION_SLIDE = {
    "kind": "explanation",
    "passageId": "toeic.listening.part3.20260809.0001",
    "index": 1,
    "questionNumber": 1,
    "totalQuestions": 2,
    "answerLabel": "A",
    "explanation": "理由はこちら。",
    "soundPath": "/home/user/academic-infra/.academic-audio/jobs/x/a1.wav",
    "durationSeconds": 10.0,
    "captionsEn": [{"start": 0, "end": 5, "text": "The answer is A."}],
    "captionsJa": [{"start": 0, "end": 5, "text": "理由はこちら。"}],
}

PRONUNCIATION_SLIDE = {
    "kind": "pronunciation",
    "passageId": "toeic.listening.part3.20260809.0001",
    "index": 1,
    "points": [{"phrase": "went out", "note_en": "links together", "note_ja": "つながります"}],
    "soundPath": "/home/user/academic-infra/.academic-audio/jobs/x/pronunciation.wav",
    "durationSeconds": 10.0,
    "captionsEn": [{"start": 0, "end": 5, "text": "Notice."}],
    "captionsJa": [{"start": 0, "end": 5, "text": "注目。"}],
}

SHADOWING_SLIDE = {
    "kind": "shadowing",
    "passageId": "toeic.listening.part3.20260809.0001",
    "index": 1,
    "transcript": [{"speaker": "A", "text": "Hello there."}],
    "soundPath": "/home/user/academic-infra/.academic-audio/jobs/x/shadowing.wav",
    "durationSeconds": 10.0,
    "captionsEn": [{"start": 0, "end": 5, "text": "Hello there."}],
    "captionsJa": [],
}

ALL_SLIDES = [QUESTION_SLIDE, EXPLANATION_SLIDE, PRONUNCIATION_SLIDE, SHADOWING_SLIDE]


def test_no_slides_is_rejected():
    with pytest.raises(ValueError):
        render_project_tsx([], framescript_root=None)  # type: ignore[arg-type]


def test_all_four_slide_kinds_are_embedded(tmp_path):
    tsx = render_project_tsx(ALL_SLIDES, framescript_root=tmp_path)
    for kind in ("question", "explanation", "pronunciation", "shadowing"):
        assert f'"kind": "{kind}"' in tsx


def test_all_four_scene_components_and_types_are_present(tmp_path):
    tsx = render_project_tsx(ALL_SLIDES, framescript_root=tmp_path)
    for name in ("QuestionScene", "ExplanationScene", "PronunciationScene", "ShadowingScene"):
        assert name in tsx
    for type_name in ("QuestionSlide", "ExplanationSlide", "PronunciationSlide", "ShadowingSlide"):
        assert f"type {type_name} = {{" in tsx


def test_question_and_explanation_slides_carry_a_single_question_not_a_list(tmp_path):
    """2026-08-12: 3問を1枚にまとめると密度過多だった指摘への対応、1問=1枚。"""
    tsx = render_project_tsx(ALL_SLIDES, framescript_root=tmp_path)
    assert '"questionNumber": 1' in tsx
    assert '"totalQuestions": 2' in tsx


def test_the_layout_anchors_content_to_the_top_to_avoid_caption_overlap(tmp_path):
    """2026-08-12: 中央寄せだと選択肢/解説が下端の字幕帯と重なった指摘への対応。"""
    tsx = render_project_tsx(ALL_SLIDES, framescript_root=tmp_path)
    assert 'justifyContent: "flex-start"' in tsx
