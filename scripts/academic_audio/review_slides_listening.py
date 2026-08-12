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

字幕は文単位に分割する(2026-08-12「字幕が大きくなりすぎている」の指摘への対応)。
選択肢は画面上にカードで表示済みなので字幕には含めない(4択を1つのcueに詰めると
必ず画面からはみ出すため)。発音スライドは「該当する時だけ」ではなく毎回出す、
という明示の指示に基づく。リンキングのアニメーション等の個別演出は別途
(この器の対象外)。
"""

from __future__ import annotations

import wave
from pathlib import Path

from ._caption_cues import EN_SENTENCE_SPLIT, JA_SENTENCE_SPLIT, sentence_cues
from .engines import TTSEngine
from .models import DialogueSegment
from .pronunciation import normalize
from .renderer import concatenate_wav

_LETTERS = "ABCD"
_SLIDE_GAP_SECONDS = 0.6
# review_slides.py と同じ理由(音声終了直後の切り替えはテンポが速すぎる)で揃える。
_SLIDE_TAIL_SECONDS = 3.0

_REQUIRED_CONTENT_FIELDS = (
    "reason_en", "question_ja", "points",
    "pronunciation_intro_en", "pronunciation_intro_ja", "pronunciation_points",
)
_PER_QUESTION_FIELDS = ("reason_en", "question_ja", "points")


class ReviewSlideError(ValueError):
    pass


def _wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / handle.getframerate()


def _validate_content(passage_id: str, content: dict, question_count: int) -> None:
    missing = [key for key in _REQUIRED_CONTENT_FIELDS if key not in content]
    if missing:
        raise ReviewSlideError(f"{passage_id} の authored content に {', '.join(missing)} がありません。")
    for field in _PER_QUESTION_FIELDS:
        if len(content[field]) != question_count:
            raise ReviewSlideError(
                f"{passage_id} の {field} は設問数({question_count})と同じ数だけ必要です"
                f"(実際: {len(content[field])})。"
            )


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


def _passage_slide(passage: dict, audio_dir: Path, engine: TTSEngine) -> dict:
    """会話/スピーチ本文を、設問に入る前にまず聴かせる1枚(2026-08-12「設問の前提と
    なる会話やスピーチのスライドがあってもいい」の指摘への対応)。シャドーイング枚
    (末尾、練習用にハイライトしながら聴く)とは役割が違うので、台本の再利用に
    留め、画面上はハイライト無しの静的な書き起こしにする。"""
    passage_id = passage["passageId"]
    transcript = passage["transcript"]
    parts = [
        _render_segment(engine, audio_dir, f"{passage_id}.passage.intro", "narrator", passage["introEn"], "en")
    ] + [
        _render_segment(engine, audio_dir, f"{passage_id}.passage.{i}", line["speaker"], line["text"], "en")
        for i, line in enumerate(transcript)
    ]
    merged, durations = _merge(audio_dir, f"{passage_id}.passage.wav", parts)
    texts = [passage["introEn"]] + [line["text"] for line in transcript]
    cues_en = []
    cursor = 0.0
    for text, duration in zip(texts, durations):
        cues_en.append({"start": round(cursor, 3), "end": round(cursor + duration, 3), "text": text})
        cursor += duration + _SLIDE_GAP_SECONDS
    duration = cues_en[-1]["end"] + _SLIDE_TAIL_SECONDS
    return {
        "kind": "passage",
        "passageId": passage_id,
        "introEn": passage["introEn"],
        "transcript": transcript,
        "soundPath": str(merged),
        "durationSeconds": round(duration, 3),
        "captionsEn": cues_en,
        "captionsJa": [],
    }


def _question_slide(
    passage: dict, question_number: int, question: dict, question_ja: str, audio_dir: Path, engine: TTSEngine
) -> dict:
    """1問だけを乗せるスライド。会話全体で1度だけ話される案内文(introEn)は最初の
    設問のスライドにだけ含める(実際のTOEICの進行と同じ)。選択肢は音声には含めるが
    字幕には出さない(画面上に既にカードで出ているのに加えて4択ぶんを1つの字幕cueに
    詰めると必ずはみ出すため)。"""
    passage_id = passage["passageId"]
    total = len(passage["questions"])
    choice_text = " ".join(f"{_LETTERS[j]}, {c}." for j, c in enumerate(question["choices"]))
    question_line = f"Number {question_number}. {question['question']}"

    labeled_parts = ([("intro", passage["introEn"])] if question_number == 1 else []) + [
        ("question", question_line),
        ("choices", choice_text),
    ]
    parts = [
        _render_segment(engine, audio_dir, f"{passage_id}.q{question_number}.{label}", "narrator", text, "en")
        for label, text in labeled_parts
    ]
    merged, durations = _merge(audio_dir, f"{passage_id}.q{question_number}.wav", parts)

    cues_en: list[dict] = []
    cues_ja: list[dict] = []
    cursor = 0.0
    for (label, text), duration in zip(labeled_parts, durations):
        if label == "intro":
            cues_en.append({"start": round(cursor, 3), "end": round(cursor + duration, 3), "text": text})
        elif label == "question":
            cues_en.append({"start": round(cursor, 3), "end": round(cursor + duration, 3), "text": text})
            cues_ja.append({"start": round(cursor, 3), "end": round(cursor + duration, 3), "text": question_ja})
        # "choices" はここでは字幕を出さない(音声のみ、選択肢は画面のカードで読む)。
        cursor += duration + _SLIDE_GAP_SECONDS

    duration = sum(durations) + _SLIDE_GAP_SECONDS * (len(durations) - 1) + _SLIDE_TAIL_SECONDS
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
    passage: dict,
    question_number: int,
    question: dict,
    reason_en: str,
    points: list[dict],
    audio_dir: Path,
    engine: TTSEngine,
) -> dict:
    """points: `[{label, text}]` — 正解の理由だけでなく他の選択肢がなぜ違うかも含めた
    構造化された短い要点(Part5のAnswerSlide.pointsと同じ役割)。答えの文字だけを
    大きく出すのは解説として粒度が低いという指摘(2026-08-12)への対応。"""
    passage_id = passage["passageId"]
    total = len(passage["questions"])
    letter = _LETTERS[question["answerIndex"]]
    lead_en = f"The answer to number {question_number}. is {letter}."
    text_en = f"{lead_en} {reason_en}"

    part = _render_segment(engine, audio_dir, f"{passage_id}.a{question_number}.src", "narrator", text_en, "en")
    merged, durations = _merge(audio_dir, f"{passage_id}.a{question_number}.wav", [part])
    duration_seconds = durations[0]

    cues_en = sentence_cues(text_en, duration_seconds, EN_SENTENCE_SPLIT)
    cues_ja = sentence_cues(question["explanation"], duration_seconds, JA_SENTENCE_SPLIT)
    total_duration = duration_seconds + _SLIDE_TAIL_SECONDS
    return {
        "kind": "explanation",
        "passageId": passage_id,
        "questionNumber": question_number,
        "totalQuestions": total,
        "answerLabel": letter,
        "points": points,
        "soundPath": str(merged),
        "durationSeconds": round(total_duration, 3),
        "captionsEn": cues_en,
        "captionsJa": cues_ja,
    }


def _pronunciation_slide(passage: dict, content: dict, audio_dir: Path, engine: TTSEngine) -> dict:
    """points[i]["example_en"]: そのフレーズを実際に使った例文。フレーズの説明だけ
    でなく、例文でどう聞こえるかを音声つきで示してほしいという指摘(2026-08-12)への
    対応。説明と例文を1つの音声にまとめ、文単位のcue分割(sentence_cues)で
    自然に2つの字幕に分かれる(説明文・例文とも `.` で終わる前提)。"""
    passage_id = passage["passageId"]
    points = content["pronunciation_points"]
    texts_en = [content["pronunciation_intro_en"]] + [
        f"{p['note_en']} For example: {p['example_en']}" for p in points
    ]
    parts = [
        _render_segment(engine, audio_dir, f"{passage_id}.pron{i}", "narrator", text, "en")
        for i, text in enumerate(texts_en)
    ]
    merged, durations = _merge(audio_dir, f"{passage_id}.pronunciation.wav", parts)

    cues_en: list[dict] = []
    cues_ja: list[dict] = []
    texts_ja = [content["pronunciation_intro_ja"]] + [
        p["note_ja"] for p in points
    ]
    cursor = 0.0
    for text_en, text_ja, duration in zip(texts_en, texts_ja, durations):
        cues_en.extend(sentence_cues(text_en, duration, EN_SENTENCE_SPLIT, offset=cursor))
        cues_ja.extend(sentence_cues(text_ja, duration, JA_SENTENCE_SPLIT, offset=cursor))
        cursor += duration + _SLIDE_GAP_SECONDS

    last_end = max((c["end"] for c in cues_en + cues_ja), default=0.0)
    duration = last_end + _SLIDE_TAIL_SECONDS
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
    cues_en = []
    cursor = 0.0
    for line, duration in zip(transcript, durations):
        cues_en.append({"start": round(cursor, 3), "end": round(cursor + duration, 3), "text": line["text"]})
        cursor += duration + _SLIDE_GAP_SECONDS
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
    question_ja: [設問ごとの日本語訳], points: [設問ごとの [{label, text}]
    (正解の理由だけでなく他の選択肢がなぜ違うかも含めた短い要点、画面に出す分)],
    pronunciation_intro_en, pronunciation_intro_ja,
    pronunciation_points: [{phrase, note_en, note_ja}]}}` — Claudeが1パッセージずつ
    書いたもの(reason_en/question_ja/points/pronunciationは機械的には書けない)。

    1パッセージにつき Passage(会話/スピーチ本文の通し聴き), Q1, A1, Q2, A2, ... ,
    Pronunciation, Shadowing の順で返す(設問ごとに即座に解説することでスライド
    1枚あたりの密度を抑える)。
    """
    audio_dir.mkdir(parents=True, exist_ok=True)
    slides: list[dict] = []

    for index, passage in enumerate(passages, start=1):
        passage_id = passage["passageId"]
        content = content_by_passage_id.get(passage_id)
        if content is None:
            raise ReviewSlideError(f"{passage_id} の authored content がありません。")
        _validate_content(passage_id, content, len(passage["questions"]))

        passage_slides: list[dict] = [_passage_slide(passage, audio_dir, engine)]
        for question_number, (question, reason_en, question_ja, points) in enumerate(
            zip(passage["questions"], content["reason_en"], content["question_ja"], content["points"]), start=1
        ):
            passage_slides.append(
                _question_slide(passage, question_number, question, question_ja, audio_dir, engine)
            )
            passage_slides.append(
                _explanation_slide(passage, question_number, question, reason_en, points, audio_dir, engine)
            )
        passage_slides.append(_pronunciation_slide(passage, content, audio_dir, engine))
        passage_slides.append(_shadowing_slide(passage, audio_dir, engine))

        for slide in passage_slides:
            slide["index"] = index
            slides.append(slide)

    return slides
