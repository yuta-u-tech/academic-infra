"""スライド配列 -> FrameScriptのproject.tsx（review_slides_tsx.py）。"""

import pytest

from academic_audio.review_slides_tsx import render_project_tsx

QUESTION_SLIDE = {
    "kind": "question",
    "reviewId": "toeic.part5.20260810.0005",
    "index": 1,
    "sentence": "The new policy applies to all staff ____ of their department.",
    "choices": ["regardless", "despite", "in spite", "notwithstanding"],
    "soundPath": "/home/user/academic-infra/.academic-audio/jobs/x/toeic.part5.20260810.0005.slide1.wav",
    "durationSeconds": 10.0,
    "captionsEn": [{"start": 0, "end": 5, "text": "Question 1."}],
    "captionsJa": [{"start": 0, "end": 5, "text": "問題1。"}],
}

ANSWER_SLIDE = {
    "kind": "answer",
    "reviewId": "toeic.part5.20260810.0005",
    "answerLabel": "A",
    "answerWord": "regardless",
    "points": [{"label": "A", "text": "fits naturally"}],
    "example": "Regardless of the weather, the event proceeds.",
    "soundPath": "/home/user/academic-infra/.academic-audio/jobs/x/toeic.part5.20260810.0005.slide2.wav",
    "durationSeconds": 20.0,
    "captionsEn": [{"start": 0, "end": 5, "text": "The answer is A."}],
    "captionsJa": [{"start": 0, "end": 5, "text": "正解はAです。"}],
}


def test_no_slides_is_rejected():
    with pytest.raises(ValueError):
        render_project_tsx([], framescript_root=None)  # type: ignore[arg-type]


def test_the_slides_array_is_embedded_as_json(tmp_path):
    tsx = render_project_tsx([QUESTION_SLIDE, ANSWER_SLIDE], framescript_root=tmp_path)
    assert "const SLIDES: Slide[] = [" in tsx
    assert "regardless" in tsx
    assert '"kind": "question"' in tsx
    assert '"kind": "answer"' in tsx


def test_sound_paths_are_rewritten_relative_to_framescript_root(tmp_path):
    home = tmp_path / "home" / "user"
    framescript_root = home / "FrameScript"
    slide = {**QUESTION_SLIDE, "soundPath": str(home / "academic-infra/.academic-audio/jobs/x/slide1.wav")}
    tsx = render_project_tsx([slide], framescript_root=framescript_root)
    assert str(home) not in tsx.split('"soundPath"')[1].split(",")[0]
    assert "../academic-infra/.academic-audio/jobs/x/slide1.wav" in tsx


def test_slide_kind_type_definitions_are_present(tmp_path):
    tsx = render_project_tsx([QUESTION_SLIDE, ANSWER_SLIDE], framescript_root=tmp_path)
    assert "type QuestionSlide = {" in tsx
    assert "type AnswerSlide = {" in tsx
    assert "export const PROJECT = () => {" in tsx
