"""間違えたTOEICリスニング問題(Part3/4)から、FrameScriptで動画化するスライド一式を
組み立てる。Part5用の `review_slides.py` とは別テンプレート
(2026-08-11「リスニングについてはreadingと混ぜると大変そうなのでこちらは別の
テンプレートを作ることにしましょう」)。

DBの `ListeningItem` には会話の台本(誰が何を話したか)が残っていない
(academic_english_dataが正本)ので、呼び出し側が `academic-english-data` の
`dialogue.json` から台本を拾い直し、`PassageGroup` の形に組み立てて渡す
(この器はその変換の結果を受け取るだけで、academic-english-data には触れない)。

1パッセージ(1会話・複数設問) = 質問と解説を設問ごとに1枚ずつ(Q1/A1/Q2/A2/...) +
発音1枚 + シャドーイング1枚。最初は「1枚目は質問、2枚目で解説」で全設問をまとめて
1枚に乗せていたが、3問+選択肢を1枚に全部乗せると字幕と重なるほど密度過多になった
(2026-08-12の指摘、プロトタイプ視聴後)ため、Part5と同じく1問=1枚に割った。
発音スライドは「該当する時だけ」ではなく毎回出す、という明示の指示に基づく。
リンキングのアニメーション等の個別演出は別途(この器の対象外)。
"""

from __future__ import annotations

import wave
from pathlib import Path

from .engines import TTSEngine
from .models import DialogueSegment
from .pronunciation import normalize
from .renderer import concatenate_wav

_LETTERS = "ABCD"
_SLIDE_GAP_SECONDS = 0.6
# review_slides.py と同じ理由(音声終了直後の切り替えはテンポが速すぎる)で揃える。
_SLIDE_TAIL_SECONDS = 3.0

_REQUIRED_CONTENT_FIELDS = ("reason_en", "pronunciation_intro_en", "pronunciation_points")


class ReviewSlideError(ValueError):
    pass


def _wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / handle.getframerate()


def _validate_content(passage_id: str, content: dict, question_count: int) -> None:
    missing = [key for key in _REQUIRED_CONTENT_FIELDS if key not in content]
    if missing:
        raise ReviewSlideError(f"{passage_id} の authored content に {', '.join(missing)} がありません。")
    if len(content["reason_en"]) != question_count:
        raise ReviewSlideError(
            f"{passage_id} の reason_en は設問数({question_count})と同じ数だけ必要です"
            f"(実際: {len(content['reason_en'])})。"
        )


def _sequential_cues(texts: list[str], durations: list[float], gap: float = _SLIDE_GAP_SECONDS) -> list[dict]:
    cues = []
    cursor = 0.0
    for text, duration in zip(texts, durations):
        cues.append({"start": round(cursor, 3), "end": round(cursor + duration, 3), "text": text})
        cursor += duration + gap
    return cues


def _render_segment(engine: TTSEngine, audio_dir: Path, seg_id: str, speaker: str, text: str, language: str) -> Path:
    out = audio_dir / f"{seg_id}.wav"
    engine.render(
        DialogueSegment(id=seg_id, speaker=speaker, language=language, text=normalize(text)), out
    )
    return out


def _merge(audio_dir: Path, name: str, parts: list[Path]) -> tuple[Path, list[float]]:
    durations = [_wav_seconds(p) for p in parts]
    merged = audio_dir / name
    concatenate_wav([(p, _SLIDE_GAP_SECONDS) for p in parts[:-1]] + [(parts[-1], 0.0)], merged)
    return merged, durations


def _question_slide(passage: dict, question_number: int, question: dict, audio_dir: Path, engine: TTSEngine) -> dict:
    """1問だけを乗せるスライド。会話全体で1度だけ話される案内文(introEn)は最初の
    設問のスライドにだけ含める(実際のTOEICの進行と同じ)。"""
    passage_id = passage["passageId"]
    total = len(passage["questions"])
    choice_text = " ".join(f"{_LETTERS[j]}, {c}." for j, c in enumerate(question["choices"]))
    texts_en = ([passage["introEn"]] if question_number == 1 else []) + [
        f"Number {question_number}. {question['question']} {choice_text}"
    ]
    texts_ja = ([passage["introEn"]] if question_number == 1 else []) + [question["question"]]

    parts = [
        _render_segment(engine, audio_dir, f"{passage_id}.q{question_number}.{i}", "narrator", text, "en")
        for i, text in enumerate(texts_en)
    ]
    merged, durations = _merge(audio_dir, f"{passage_id}.q{question_number}.wav", parts)
    cues_en = _sequential_cues(texts_en, durations)
    cues_ja = _sequential_cues(texts_ja, durations)
    duration = cues_en[-1]["end"] + _SLIDE_TAIL_SECONDS
    return {
        "kind": "question",
        "passageId": passage_id,
        "questionNumber": question_number,
        "totalQuestions": total,
        "question": question["question"],
        "choices": question["choices"],
        "reviewId": question["reviewId"],
        "soundPath": str(merged),
        "durationSeconds": round(duration, 3),
        "captionsEn": cues_en,
        "captionsJa": cues_ja,
    }


def _explanation_slide(
    passage: dict, question_number: int, question: dict, reason_en: str, audio_dir: Path, engine: TTSEngine
) -> dict:
    passage_id = passage["passageId"]
    total = len(passage["questions"])
    letter = _LETTERS[question["answerIndex"]]
    text_en = f"The answer to number {question_number}. is {letter}. {reason_en}"

    part = _render_segment(engine, audio_dir, f"{passage_id}.a{question_number}.src", "narrator", text_en, "en")
    merged, durations = _merge(audio_dir, f"{passage_id}.a{question_number}.wav", [part])
    cues_en = _sequential_cues([text_en], durations)
    cues_ja = _sequential_cues([question["explanation"]], durations)
    duration = cues_en[-1]["end"] + _SLIDE_TAIL_SECONDS
    return {
        "kind": "explanation",
        "passageId": passage_id,
        "questionNumber": question_number,
        "totalQuestions": total,
        "answerLabel": letter,
        "explanation": question["explanation"],
        "soundPath": str(merged),
        "durationSeconds": round(duration, 3),
        "captionsEn": cues_en,
        "captionsJa": cues_ja,
    }


def _pronunciation_slide(passage: dict, content: dict, audio_dir: Path, engine: TTSEngine) -> dict:
    passage_id = passage["passageId"]
    points = content["pronunciation_points"]
    texts_en = [content["pronunciation_intro_en"]] + [p["note_en"] for p in points]
    parts = [
        _render_segment(engine, audio_dir, f"{passage_id}.pron{i}", "narrator", text, "en")
        for i, text in enumerate(texts_en)
    ]
    merged, durations = _merge(audio_dir, f"{passage_id}.pronunciation.wav", parts)
    cues_en = _sequential_cues(texts_en, durations)
    cues_ja = _sequential_cues(
        [content.get("pronunciation_intro_ja", content["pronunciation_intro_en"])]
        + [p["note_ja"] for p in points],
        durations,
    )
    duration = cues_en[-1]["end"] + _SLIDE_TAIL_SECONDS
    return {
        "kind": "pronunciation",
        "passageId": passage_id,
        "points": points,
        "soundPath": str(merged),
        "durationSeconds": round(duration, 3),
        "captionsEn": cues_en,
        "captionsJa": cues_ja,
    }


def _shadowing_slide(passage: dict, audio_dir: Path, engine: TTSEngine) -> dict:
    passage_id = passage["passageId"]
    transcript = passage["transcript"]
    parts = [
        _render_segment(engine, audio_dir, f"{passage_id}.sh{i}", line["speaker"], line["text"], "en")
        for i, line in enumerate(transcript)
    ]
    merged, durations = _merge(audio_dir, f"{passage_id}.shadowing.wav", parts)
    cues_en = _sequential_cues([line["text"] for line in transcript], durations)
    duration = cues_en[-1]["end"] + _SLIDE_TAIL_SECONDS
    return {
        "kind": "shadowing",
        "passageId": passage_id,
        "transcript": transcript,
        "soundPath": str(merged),
        "durationSeconds": round(duration, 3),
        "captionsEn": cues_en,
        "captionsJa": [],
    }


def build_slides_listening(
    passages: list[dict],
    content_by_passage_id: dict[str, dict],
    audio_dir: Path,
    engine: TTSEngine,
) -> list[dict]:
    """passages: `{passageId, part, introEn, transcript: [{speaker, text}],
    questions: [{reviewId, question, choices, answerIndex, explanation}]}` の配列
    (academic-english-data の dialogue.json/answers.json から呼び出し側が組み立てる)。

    content_by_passage_id: `{passageId: {reason_en: [設問ごとの英語ナレーション],
    pronunciation_intro_en, pronunciation_points: [{phrase, note_en, note_ja}]}}`
    — Claudeが1パッセージずつ書いたもの(reason_enとpronunciationは機械的には書けない)。

    1パッセージにつき Q1, A1, Q2, A2, ... , Pronunciation, Shadowing の順で返す
    (設問ごとに即座に解説することでスライド1枚あたりの密度を抑える)。
    """
    audio_dir.mkdir(parents=True, exist_ok=True)
    slides: list[dict] = []

    for index, passage in enumerate(passages, start=1):
        passage_id = passage["passageId"]
        content = content_by_passage_id.get(passage_id)
        if content is None:
            raise ReviewSlideError(f"{passage_id} の authored content がありません。")
        _validate_content(passage_id, content, len(passage["questions"]))

        passage_slides: list[dict] = []
        for question_number, (question, reason_en) in enumerate(
            zip(passage["questions"], content["reason_en"]), start=1
        ):
            passage_slides.append(_question_slide(passage, question_number, question, audio_dir, engine))
            passage_slides.append(
                _explanation_slide(passage, question_number, question, reason_en, audio_dir, engine)
            )
        passage_slides.append(_pronunciation_slide(passage, content, audio_dir, engine))
        passage_slides.append(_shadowing_slide(passage, audio_dir, engine))

        for slide in passage_slides:
            slide["index"] = index
            slides.append(slide)

    return slides
