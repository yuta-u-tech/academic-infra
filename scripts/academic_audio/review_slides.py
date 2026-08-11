"""間違えたTOEIC問題から、FrameScriptで動画化するスライド一式を組み立てる。

「なぜその答えなのか」を短い英語ナレーション(reason_en)とオンスクリーンの
要点(points)にまとめるのは機械的には書けない判断なので、Claudeが1問ずつ書く
（generate.py の request/ingest と同じ役割分担 — ここは器だけ）。日本語字幕は
DBに既にある explanation をそのまま使う(二重に書く必要をなくす)。

1問 = 2枚(Question/Answer)のスライドデータを作り、音声合成・音声結合・
字幕タイミング計算まで済ませる。TSX自体の組み立ては review_slides_tsx.py。
"""

from __future__ import annotations

import json
import re
import wave
from pathlib import Path

from .engines import TTSEngine
from .models import DialogueSegment
from .pronunciation import normalize
from .renderer import concatenate_wav

_LETTERS = "ABCD"
_EN_SENTENCE_SPLIT = re.compile(r"(?<=[.!?]) ")
_JA_SENTENCE_SPLIT = re.compile(r"(?<=。)")
_SLIDE_GAP_SECONDS = 0.6
# スライドの音声が終わってから次のスライドへ切り替わるまでの無音の間。
# 音声が終わった瞬間に次に切り替わるとテンポが速すぎるという指摘を受けて追加
# （字幕を読み終える余韻・次の問題への切り替わりを意識させる間）。
_SLIDE_TAIL_SECONDS = 3.0


class ReviewSlideError(ValueError):
    pass


def _wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / handle.getframerate()


def _sentence_cues(text: str, duration: float, split_pattern: re.Pattern, offset: float = 0.0) -> list[dict]:
    """英語は `. `、日本語は `。` の直後で分け、文字数に比例して時間を割る。

    音声そのものと1対1で対応しない字幕(日本語訳)にも使うため、厳密な同期ではなく
    近似でよい前提（`toeic_review.py` の render_tex と同じ「読める範囲で足りる」方針）。
    """
    sentences = [s.strip() for s in split_pattern.split(text) if s.strip()]
    if not sentences:
        return [{"start": round(offset, 3), "end": round(offset + duration, 3), "text": text.strip()}]
    total_chars = sum(len(s) for s in sentences) or 1
    cues = []
    cursor = offset
    for sentence in sentences:
        span = duration * (len(sentence) / total_chars)
        cues.append({"start": round(cursor, 3), "end": round(cursor + span, 3), "text": sentence})
        cursor += span
    return cues


_REQUIRED_CONTENT_FIELDS = ("reason_en", "points", "question_ja", "choices_ja")


def _validate_content(review_id: str, content: dict) -> None:
    missing = [key for key in _REQUIRED_CONTENT_FIELDS if key not in content]
    if missing:
        raise ReviewSlideError(f"{review_id} の authored content に {', '.join(missing)} がありません。")


def build_slides(
    items: list[dict],
    content_by_review_id: dict[str, dict],
    audio_dir: Path,
    engine: TTSEngine,
) -> list[dict]:
    """items: `acenglish.toeic_review.fetch_wrong_items()` の出力。

    content_by_review_id: `{review_id: {reason_en, points, question_ja, choices_ja,
    answer_ja?, example?}}` — Claudeが1問ずつ書いたもの。
    """
    audio_dir.mkdir(parents=True, exist_ok=True)
    slides: list[dict] = []

    for index, row in enumerate(items, start=1):
        payload = json.loads(row["payload"])
        review_id = row["review_id"]
        content = content_by_review_id.get(review_id)
        if content is None:
            raise ReviewSlideError(f"{review_id} の authored content がありません。")
        _validate_content(review_id, content)

        choices = payload["choices"]
        answer_index = payload["answer_index"]
        letter = _LETTERS[answer_index]
        answer = choices[answer_index]
        sentence_blank = payload["sentence"].replace("____", "blank")
        question_text_en = f"Question {index}. {sentence_blank}"
        choice_text_en = " ".join(f"{_LETTERS[j]}, {choice}." for j, choice in enumerate(choices))
        answer_text_en = f"The answer is {letter}, {answer}."

        def _render(text: str, seg_id: str) -> Path:
            out = audio_dir / f"{review_id}.{seg_id}.wav"
            engine.render(
                DialogueSegment(id=seg_id, speaker="narrator", language="en", text=normalize(text)), out
            )
            return out

        q_wav = _render(question_text_en, "question")
        c_wav = _render(choice_text_en, "choices")
        a_wav = _render(answer_text_en, "answer")
        r_wav = _render(content["reason_en"], "reason")

        q_dur, c_dur = _wav_seconds(q_wav), _wav_seconds(c_wav)
        a_dur, r_dur = _wav_seconds(a_wav), _wav_seconds(r_wav)

        slide1_wav = audio_dir / f"{review_id}.slide1.wav"
        concatenate_wav([(q_wav, _SLIDE_GAP_SECONDS), (c_wav, 0.0)], slide1_wav)
        slide2_wav = audio_dir / f"{review_id}.slide2.wav"
        concatenate_wav([(a_wav, _SLIDE_GAP_SECONDS), (r_wav, 0.0)], slide2_wav)

        slide1_duration = q_dur + _SLIDE_GAP_SECONDS + c_dur + _SLIDE_TAIL_SECONDS
        slide2_duration = a_dur + _SLIDE_GAP_SECONDS + r_dur + _SLIDE_TAIL_SECONDS
        choices_start = q_dur + _SLIDE_GAP_SECONDS
        reason_start = a_dur + _SLIDE_GAP_SECONDS

        slides.append(
            {
                "kind": "question",
                "reviewId": review_id,
                "index": index,
                "sentence": payload["sentence"],
                "choices": choices,
                "soundPath": str(slide1_wav),
                "durationSeconds": round(slide1_duration, 3),
                "captionsEn": [
                    {"start": 0, "end": round(q_dur, 3), "text": question_text_en},
                    {
                        "start": round(choices_start, 3),
                        "end": round(choices_start + c_dur, 3),
                        "text": choice_text_en,
                    },
                ],
                "captionsJa": [
                    {"start": 0, "end": round(q_dur, 3), "text": content["question_ja"]},
                    {
                        "start": round(choices_start, 3),
                        "end": round(choices_start + c_dur, 3),
                        "text": content["choices_ja"],
                    },
                ],
            }
        )
        slides.append(
            {
                "kind": "answer",
                "reviewId": review_id,
                "answerLabel": letter,
                "answerWord": answer,
                "points": content["points"],
                "example": content.get("example", ""),
                "soundPath": str(slide2_wav),
                "durationSeconds": round(slide2_duration, 3),
                "captionsEn": [
                    {"start": 0, "end": round(a_dur, 3), "text": answer_text_en},
                    *_sentence_cues(content["reason_en"], r_dur, _EN_SENTENCE_SPLIT, offset=reason_start),
                ],
                "captionsJa": [
                    {
                        "start": 0,
                        "end": round(a_dur, 3),
                        "text": content.get("answer_ja", f"正解は{letter}、{answer} です。"),
                    },
                    *_sentence_cues(payload["explanation"], r_dur, _JA_SENTENCE_SPLIT, offset=reason_start),
                ],
            }
        )

    return slides
