"""間違えたTOEIC Part2の問題から、FrameScriptで動画化するスライド一式を組み立てる。

Part3/4(`review_slides_listening.py`)は1会話を挟むので4枚固定(質問/解説/発音/
シャドーイング)にしたが、Part2には共有パッセージが無い(発言1つ+応答3つだけ)ので、
3枚固定(質問/解説/発音)に留める。シャドーイングは無し
(2026-08-12「それでok」で確定)。
"""

from __future__ import annotations

import wave
from pathlib import Path

from .engines import TTSEngine
from .models import DialogueSegment
from .pronunciation import normalize
from .renderer import concatenate_wav

_LETTERS = "ABC"
_SLIDE_GAP_SECONDS = 0.6
_SLIDE_TAIL_SECONDS = 3.0

_REQUIRED_CONTENT_FIELDS = ("reason_en", "pronunciation_intro_en", "pronunciation_points")


class ReviewSlideError(ValueError):
    pass


def _wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / handle.getframerate()


def _validate_content(review_id: str, content: dict) -> None:
    missing = [key for key in _REQUIRED_CONTENT_FIELDS if key not in content]
    if missing:
        raise ReviewSlideError(f"{review_id} の authored content に {', '.join(missing)} がありません。")


def _sequential_cues(texts: list[str], durations: list[float], gap: float = _SLIDE_GAP_SECONDS) -> list[dict]:
    cues = []
    cursor = 0.0
    for text, duration in zip(texts, durations):
        cues.append({"start": round(cursor, 3), "end": round(cursor + duration, 3), "text": text})
        cursor += duration + gap
    return cues


def _render_segment(engine: TTSEngine, audio_dir: Path, seg_id: str, text: str) -> Path:
    out = audio_dir / f"{seg_id}.wav"
    engine.render(DialogueSegment(id=seg_id, speaker="narrator", language="en", text=normalize(text)), out)
    return out


def _merge(audio_dir: Path, name: str, parts: list[Path]) -> tuple[Path, list[float]]:
    durations = [_wav_seconds(p) for p in parts]
    merged = audio_dir / name
    concatenate_wav([(p, _SLIDE_GAP_SECONDS) for p in parts[:-1]] + [(parts[-1], 0.0)], merged)
    return merged, durations


def _question_slide(item: dict, audio_dir: Path, engine: TTSEngine) -> dict:
    review_id = item["reviewId"]
    choice_text = " ".join(f"{_LETTERS[j]}, {c}." for j, c in enumerate(item["choices"]))
    texts_en = [item["questionEn"], choice_text]
    parts = [
        _render_segment(engine, audio_dir, f"{review_id}.q{i}", text) for i, text in enumerate(texts_en)
    ]
    merged, durations = _merge(audio_dir, f"{review_id}.slide1.wav", parts)
    cues_en = _sequential_cues(texts_en, durations)
    duration = cues_en[-1]["end"] + _SLIDE_TAIL_SECONDS
    return {
        "kind": "question",
        "reviewId": review_id,
        "questionEn": item["questionEn"],
        "choices": item["choices"],
        "soundPath": str(merged),
        "durationSeconds": round(duration, 3),
        "captionsEn": cues_en,
        "captionsJa": [],
    }


def _explanation_slide(item: dict, content: dict, audio_dir: Path, engine: TTSEngine) -> dict:
    review_id = item["reviewId"]
    letter = _LETTERS[item["answerIndex"]]
    texts_en = [f"The answer is {letter}. {content['reason_en']}"]
    parts = [
        _render_segment(engine, audio_dir, f"{review_id}.exp{i}", text) for i, text in enumerate(texts_en)
    ]
    merged, durations = _merge(audio_dir, f"{review_id}.slide2.wav", parts)
    cues_en = _sequential_cues(texts_en, durations)
    cues_ja = _sequential_cues([item["explanation"]], durations)
    duration = cues_en[-1]["end"] + _SLIDE_TAIL_SECONDS
    return {
        "kind": "explanation",
        "reviewId": review_id,
        "answerLabel": letter,
        "explanation": item["explanation"],
        "soundPath": str(merged),
        "durationSeconds": round(duration, 3),
        "captionsEn": cues_en,
        "captionsJa": cues_ja,
    }


def _pronunciation_slide(item: dict, content: dict, audio_dir: Path, engine: TTSEngine) -> dict:
    review_id = item["reviewId"]
    points = content["pronunciation_points"]
    texts_en = [content["pronunciation_intro_en"]] + [p["note_en"] for p in points]
    parts = [
        _render_segment(engine, audio_dir, f"{review_id}.pron{i}", text) for i, text in enumerate(texts_en)
    ]
    merged, durations = _merge(audio_dir, f"{review_id}.slide3.wav", parts)
    cues_en = _sequential_cues(texts_en, durations)
    cues_ja = _sequential_cues(
        [content.get("pronunciation_intro_ja", content["pronunciation_intro_en"])]
        + [p["note_ja"] for p in points],
        durations,
    )
    duration = cues_en[-1]["end"] + _SLIDE_TAIL_SECONDS
    return {
        "kind": "pronunciation",
        "reviewId": review_id,
        "points": points,
        "soundPath": str(merged),
        "durationSeconds": round(duration, 3),
        "captionsEn": cues_en,
        "captionsJa": cues_ja,
    }


def build_slides_listening_part2(
    items: list[dict],
    content_by_review_id: dict[str, dict],
    audio_dir: Path,
    engine: TTSEngine,
) -> list[dict]:
    """items: `{reviewId, questionEn, choices, answerIndex, explanation}` の配列
    (academic-english-data の該当Part2セットから呼び出し側が組み立てる)。

    content_by_review_id: `{reviewId: {reason_en, pronunciation_intro_en,
    pronunciation_points: [{phrase, note_en, note_ja}]}}` — Claudeが1問ずつ書いたもの。
    """
    audio_dir.mkdir(parents=True, exist_ok=True)
    slides: list[dict] = []

    for index, item in enumerate(items, start=1):
        review_id = item["reviewId"]
        content = content_by_review_id.get(review_id)
        if content is None:
            raise ReviewSlideError(f"{review_id} の authored content がありません。")
        _validate_content(review_id, content)

        question_slide = _question_slide(item, audio_dir, engine)
        explanation_slide = _explanation_slide(item, content, audio_dir, engine)
        pronunciation_slide = _pronunciation_slide(item, content, audio_dir, engine)

        for slide in (question_slide, explanation_slide, pronunciation_slide):
            slide["index"] = index
            slides.append(slide)

    return slides
