"""間違えたTOEIC Part2の問題から、FrameScriptで動画化するスライド一式を組み立てる。

Part3/4(`review_slides_listening.py`)は1会話を挟むので4枚固定(質問/解説/発音/
シャドーイング)にしたが、Part2には共有パッセージが無い(発言1つ+応答3つだけ)ので、
3枚固定(質問/解説/発音)に留める。シャドーイングは無し
(2026-08-12「それでok」で確定)。

字幕は文単位に分割し(2026-08-12「字幕が大きくなりすぎている」の指摘への対応)、
選択肢は画面上にカードで表示済みなので字幕には含めない。
"""

from __future__ import annotations

import wave
from pathlib import Path

from ._caption_cues import EN_SENTENCE_SPLIT, JA_SENTENCE_SPLIT, sentence_cues
from .engines import TTSEngine
from .models import DialogueSegment
from .pronunciation import normalize
from .renderer import concatenate_wav

_LETTERS = "ABC"
_SLIDE_GAP_SECONDS = 0.6
_SLIDE_TAIL_SECONDS = 3.0

_REQUIRED_CONTENT_FIELDS = (
    "reason_en", "question_ja", "points",
    "pronunciation_intro_en", "pronunciation_intro_ja", "pronunciation_points",
)


class ReviewSlideError(ValueError):
    pass


def _wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / handle.getframerate()


def _validate_content(review_id: str, content: dict) -> None:
    missing = [key for key in _REQUIRED_CONTENT_FIELDS if key not in content]
    if missing:
        raise ReviewSlideError(f"{review_id} の authored content に {', '.join(missing)} がありません。")


def _render_segment(engine: TTSEngine, audio_dir: Path, seg_id: str, text: str) -> Path:
    out = audio_dir / f"{seg_id}.wav"
    engine.render(DialogueSegment(id=seg_id, speaker="narrator", language="en", text=normalize(text)), out)
    return out


def _merge(audio_dir: Path, name: str, parts: list[Path]) -> tuple[Path, list[float]]:
    durations = [_wav_seconds(p) for p in parts]
    merged = audio_dir / name
    concatenate_wav([(p, _SLIDE_GAP_SECONDS) for p in parts[:-1]] + [(parts[-1], 0.0)], merged)
    return merged, durations


def _question_slide(item: dict, content: dict, audio_dir: Path, engine: TTSEngine) -> dict:
    """選択肢は音声には含めるが字幕には出さない(画面のカードで既に読めるため、
    3択ぶんを1つのcueに詰めると必ずはみ出す)。"""
    review_id = item["reviewId"]
    choice_text = " ".join(f"{_LETTERS[j]}, {c}." for j, c in enumerate(item["choices"]))
    parts = [
        _render_segment(engine, audio_dir, f"{review_id}.q.question", item["questionEn"]),
        _render_segment(engine, audio_dir, f"{review_id}.q.choices", choice_text),
    ]
    merged, durations = _merge(audio_dir, f"{review_id}.slide1.wav", parts)
    question_duration = durations[0]
    duration = sum(durations) + _SLIDE_GAP_SECONDS * (len(durations) - 1) + _SLIDE_TAIL_SECONDS
    return {
        "kind": "question",
        "reviewId": review_id,
        "questionEn": item["questionEn"],
        "choices": item["choices"],
        "soundPath": str(merged),
        "durationSeconds": round(duration, 3),
        "captionsEn": [{"start": 0, "end": round(question_duration, 3), "text": item["questionEn"]}],
        "captionsJa": [{"start": 0, "end": round(question_duration, 3), "text": content["question_ja"]}],
    }


def _explanation_slide(item: dict, content: dict, audio_dir: Path, engine: TTSEngine) -> dict:
    """content["points"]: `[{label, text}]` — 正解の理由だけでなく他の選択肢が
    なぜ違うかも含めた短い要点(Part5のAnswerSlide.pointsと同じ役割)。答えの
    文字だけを大きく出すのは解説として粒度が低いという指摘(2026-08-12)への対応。"""
    review_id = item["reviewId"]
    letter = _LETTERS[item["answerIndex"]]
    text_en = f"The answer is {letter}. {content['reason_en']}"
    part = _render_segment(engine, audio_dir, f"{review_id}.exp.src", text_en)
    merged, durations = _merge(audio_dir, f"{review_id}.slide2.wav", [part])
    duration_seconds = durations[0]

    cues_en = sentence_cues(text_en, duration_seconds, EN_SENTENCE_SPLIT)
    cues_ja = sentence_cues(item["explanation"], duration_seconds, JA_SENTENCE_SPLIT)
    duration = duration_seconds + _SLIDE_TAIL_SECONDS
    return {
        "kind": "explanation",
        "reviewId": review_id,
        "answerLabel": letter,
        "points": content["points"],
        "soundPath": str(merged),
        "durationSeconds": round(duration, 3),
        "captionsEn": cues_en,
        "captionsJa": cues_ja,
    }


def _pronunciation_slide(item: dict, content: dict, audio_dir: Path, engine: TTSEngine) -> dict:
    """points[i]["example_en"]: そのフレーズを実際に使った例文。説明だけでなく
    実際の例文でどう聞こえるかを音声つきで示してほしいという指摘(2026-08-12)への
    対応(review_slides_listening.pyのPart3/4と同じ)。"""
    review_id = item["reviewId"]
    points = content["pronunciation_points"]
    texts_en = [content["pronunciation_intro_en"]] + [
        f"{p['note_en']} For example: {p['example_en']}" for p in points
    ]
    texts_ja = [content["pronunciation_intro_ja"]] + [
        p["note_ja"] for p in points
    ]
    parts = [
        _render_segment(engine, audio_dir, f"{review_id}.pron{i}", text) for i, text in enumerate(texts_en)
    ]
    merged, durations = _merge(audio_dir, f"{review_id}.slide3.wav", parts)

    cues_en: list[dict] = []
    cues_ja: list[dict] = []
    cursor = 0.0
    for text_en, text_ja, duration in zip(texts_en, texts_ja, durations):
        cues_en.extend(sentence_cues(text_en, duration, EN_SENTENCE_SPLIT, offset=cursor))
        cues_ja.extend(sentence_cues(text_ja, duration, JA_SENTENCE_SPLIT, offset=cursor))
        cursor += duration + _SLIDE_GAP_SECONDS

    last_end = max((c["end"] for c in cues_en + cues_ja), default=0.0)
    duration = last_end + _SLIDE_TAIL_SECONDS
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

    content_by_review_id: `{reviewId: {reason_en, question_ja, points: [{label, text}]
    (正解の理由だけでなく他の選択肢がなぜ違うかも含めた短い要点、画面に出す分),
    pronunciation_intro_en, pronunciation_intro_ja,
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

        question_slide = _question_slide(item, content, audio_dir, engine)
        explanation_slide = _explanation_slide(item, content, audio_dir, engine)
        pronunciation_slide = _pronunciation_slide(item, content, audio_dir, engine)

        for slide in (question_slide, explanation_slide, pronunciation_slide):
            slide["index"] = index
            slides.append(slide)

    return slides
