"""Item-centric listening materials.

作問は「1問」を単位に考えるほうが自然なので、Claude には問題の配列を書いてもらう。
そこから音声用の台本・解答・問題冊子を機械的に導く。3つを別々に書かせると必ずズレる。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .formats import ListeningFormat, PassageSlot, QuestionSlot
from .models import DialogueScript, DialogueSegment

# TOEIC の会話表記 (A, B, ...) に合わせる。話者数はここまでに制限する。
_SPEAKER_LABELS = ("A", "B", "C")


class ItemValidationError(Exception):
    pass


@dataclass(frozen=True)
class ItemPart:
    role: str
    text: str


@dataclass(frozen=True)
class ListeningItem:
    item_id: str
    parts: list[ItemPart]
    answer_index: int | None
    explanation: str
    reason: str

    def parts_with_role(self, role: str) -> list[ItemPart]:
        return [part for part in self.parts if part.role == role]


@dataclass(frozen=True)
class ListeningSet:
    format_id: str
    title: str
    source_id: str
    source_commit: str
    items: list[ListeningItem]

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_result(path: Path, listening_format: ListeningFormat) -> ListeningSet:
    """Read and validate what Claude wrote against the format definition."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ItemValidationError(f"{path} を JSON として読めません: {error}") from error
    if not isinstance(data, dict):
        raise ItemValidationError(f"{path} のトップレベルがオブジェクトではありません。")

    for key in ("title", "source_id", "items"):
        if not data.get(key):
            raise ItemValidationError(f"{path} に {key} がありません。")
    if data.get("format") and data["format"] != listening_format.id:
        raise ItemValidationError(
            f"形式が違います: ファイルは '{data['format']}'、指定は '{listening_format.id}'"
        )

    items = [_build_item(raw, index, listening_format) for index, raw in enumerate(data["items"], start=1)]
    seen = set()
    for item in items:
        if item.item_id in seen:
            raise ItemValidationError(f"item_id '{item.item_id}' が重複しています。")
        seen.add(item.item_id)

    return ListeningSet(
        format_id=listening_format.id,
        title=data["title"],
        source_id=data["source_id"],
        source_commit=data.get("source_commit", "unknown"),
        items=items,
    )


def _build_item(raw: Any, index: int, listening_format: ListeningFormat) -> ListeningItem:
    where = f"items[{index}]"
    if not isinstance(raw, dict):
        raise ItemValidationError(f"{where} がオブジェクトではありません。")
    for key in ("parts", "explanation"):
        if not raw.get(key):
            raise ItemValidationError(f"{where} に {key} がありません。")

    parts = []
    for part_index, part in enumerate(raw["parts"], start=1):
        if not isinstance(part, dict) or not part.get("role") or not part.get("text"):
            raise ItemValidationError(f"{where}.parts[{part_index}] に role か text がありません。")
        parts.append(ItemPart(role=str(part["role"]), text=str(part["text"]).strip()))

    _validate_against_format(parts, where, listening_format)
    answer_index = _validate_answer(raw, where, parts, listening_format)

    return ListeningItem(
        item_id=str(raw.get("item_id") or f"item-{index:03d}"),
        parts=parts,
        answer_index=answer_index,
        explanation=str(raw["explanation"]).strip(),
        reason=str(raw.get("reason", "")).strip(),
    )


def _validate_against_format(parts: list[ItemPart], where: str, listening_format: ListeningFormat) -> None:
    expected = [(slot.role, slot.count) for slot in listening_format.item]
    actual: list[tuple[str, int]] = []
    for part in parts:
        if actual and actual[-1][0] == part.role:
            actual[-1] = (part.role, actual[-1][1] + 1)
        else:
            actual.append((part.role, 1))
    if actual != expected:
        raise ItemValidationError(
            f"{where}: 発話の構成が形式と違います。"
            f"期待 {_describe(expected)} / 実際 {_describe(actual)}"
        )

    for part in parts:
        slot = listening_format.slot_for(part.role)
        if slot is None or slot.words is None:
            continue
        words = len(part.text.split())
        low, high = slot.words
        if not low <= words <= high:
            raise ItemValidationError(
                f"{where}: {part.role} が {words} 語です（{low}〜{high} 語）。本文: {part.text}"
            )


def _describe(pairs: list[tuple[str, int]]) -> str:
    return " + ".join(f"{role}×{count}" for role, count in pairs)


def _validate_answer(raw: dict, where: str, parts: list[ItemPart], listening_format: ListeningFormat) -> int | None:
    choices = [part for part in parts if part.role == "choice"]
    if not choices:
        return None
    answer_index = raw.get("answer_index")
    if answer_index is None:
        raise ItemValidationError(f"{where} に answer_index がありません。")
    if not isinstance(answer_index, int) or not 0 <= answer_index < len(choices):
        raise ItemValidationError(
            f"{where}: answer_index が範囲外です（0〜{len(choices) - 1}、実際 {answer_index}）"
        )
    return answer_index


def to_script(listening_set: ListeningSet, listening_format: ListeningFormat) -> DialogueScript:
    """Flatten items into the segment list the renderer consumes."""
    segments: list[DialogueSegment] = []
    for item in listening_set.items:
        for part in item.parts:
            slot = listening_format.slot_for(part.role)
            segments.append(
                DialogueSegment(
                    id=f"seg-{len(segments) + 1:03d}",
                    speaker="narrator",
                    text=part.text,
                    language=listening_format.language,
                    emotion="Neutral",
                    speed=1.0,
                    pause=slot.pause if slot else 0.5,
                    source_section=listening_set.source_id,
                    item_id=item.item_id,
                    role=part.role,
                )
            )
    return DialogueScript(
        title=listening_set.title,
        source_id=listening_set.source_id,
        source_commit=listening_set.source_commit,
        segments=segments,
    )


def to_answers(listening_set: ListeningSet) -> dict[str, Any]:
    """The grading key. Kept out of the audio on purpose."""
    return {
        "format": listening_set.format_id,
        "title": listening_set.title,
        "source_id": listening_set.source_id,
        "source_commit": listening_set.source_commit,
        "items": [
            {
                "item_id": item.item_id,
                "answer_index": item.answer_index,
                "answer_label": _label(item.answer_index),
                "answer_text": (
                    item.parts_with_role("choice")[item.answer_index].text
                    if item.answer_index is not None and item.parts_with_role("choice")
                    else None
                ),
                "explanation": item.explanation,
                "reason": item.reason,
            }
            for item in listening_set.items
        ],
    }


def _label(index: int | None) -> str | None:
    return None if index is None else chr(ord("A") + index)


# --- grouping: passage（TOEIC Part 3/4 のように、1つの音声に複数設問が続く形式）------


@dataclass(frozen=True)
class PassageLine:
    speaker: str
    text: str


@dataclass(frozen=True)
class PassageQuestion:
    text: str
    choices: list[str]
    answer_index: int
    explanation: str


@dataclass(frozen=True)
class PassageItem:
    item_id: str
    passage: list[PassageLine]
    questions: list[PassageQuestion]
    reason: str


@dataclass(frozen=True)
class PassageSet:
    format_id: str
    title: str
    source_id: str
    source_commit: str
    items: list[PassageItem]


def load_passage_result(path: Path, listening_format: ListeningFormat) -> PassageSet:
    """Read and validate a grouping: passage result (TOEIC Part 3/4 style)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ItemValidationError(f"{path} を JSON として読めません: {error}") from error
    if not isinstance(data, dict):
        raise ItemValidationError(f"{path} のトップレベルがオブジェクトではありません。")
    for key in ("title", "source_id", "items"):
        if not data.get(key):
            raise ItemValidationError(f"{path} に {key} がありません。")
    if data.get("format") and data["format"] != listening_format.id:
        raise ItemValidationError(
            f"形式が違います: ファイルは '{data['format']}'、指定は '{listening_format.id}'"
        )
    assert listening_format.passage_slot is not None and listening_format.question_slot is not None

    items = [
        _build_passage_item(raw, index, listening_format.passage_slot, listening_format.question_slot)
        for index, raw in enumerate(data["items"], start=1)
    ]
    seen: set[str] = set()
    for item in items:
        if item.item_id in seen:
            raise ItemValidationError(f"item_id '{item.item_id}' が重複しています。")
        seen.add(item.item_id)

    return PassageSet(
        format_id=listening_format.id,
        title=data["title"],
        source_id=data["source_id"],
        source_commit=data.get("source_commit", "unknown"),
        items=items,
    )


def _build_passage_item(
    raw: Any, index: int, passage_slot: PassageSlot, question_slot: QuestionSlot
) -> PassageItem:
    where = f"items[{index}]"
    if not isinstance(raw, dict):
        raise ItemValidationError(f"{where} がオブジェクトではありません。")
    for key in ("passage", "questions"):
        if not raw.get(key):
            raise ItemValidationError(f"{where} に {key} がありません。")

    lines = _build_passage_lines(raw["passage"], where, passage_slot)
    questions = [
        _build_passage_question(raw_question, where, q_index, question_slot)
        for q_index, raw_question in enumerate(raw["questions"], start=1)
    ]
    if len(questions) != question_slot.count:
        raise ItemValidationError(f"{where}.questions は {question_slot.count} 問必要です（実際: {len(questions)}）")

    return PassageItem(
        item_id=str(raw.get("item_id") or f"item-{index:03d}"),
        passage=lines,
        questions=questions,
        reason=str(raw.get("reason", "")).strip(),
    )


def _build_passage_lines(raw_lines: Any, where: str, passage_slot: PassageSlot) -> list[PassageLine]:
    lines = []
    for line_index, raw_line in enumerate(raw_lines, start=1):
        if not isinstance(raw_line, dict) or not raw_line.get("speaker") or not raw_line.get("text"):
            raise ItemValidationError(f"{where}.passage[{line_index}] に speaker か text がありません。")
        lines.append(PassageLine(speaker=str(raw_line["speaker"]), text=str(raw_line["text"]).strip()))

    allowed = _SPEAKER_LABELS[: passage_slot.speakers]
    unknown = sorted({line.speaker for line in lines} - set(allowed))
    if unknown:
        raise ItemValidationError(
            f"{where}.passage: 話者は {', '.join(allowed)} だけ使えます（不明: {', '.join(unknown)}）"
        )

    low, high = passage_slot.turns
    if not low <= len(lines) <= high:
        raise ItemValidationError(f"{where}.passage: 発話数が{len(lines)}です（{low}〜{high}）")

    wlow, whigh = passage_slot.words_per_turn
    for line_index, line in enumerate(lines, start=1):
        words = len(line.text.split())
        if not wlow <= words <= whigh:
            raise ItemValidationError(
                f"{where}.passage[{line_index}] が {words} 語です（{wlow}〜{whigh} 語）。本文: {line.text}"
            )
    return lines


def _build_passage_question(raw: Any, where: str, q_index: int, question_slot: QuestionSlot) -> PassageQuestion:
    sub_where = f"{where}.questions[{q_index}]"
    if not isinstance(raw, dict) or not raw.get("text") or not raw.get("choices") or not raw.get("explanation"):
        raise ItemValidationError(f"{sub_where} に text/choices/explanation のいずれかがありません。")

    text = str(raw["text"]).strip()
    words = len(text.split())
    low, high = question_slot.words
    if not low <= words <= high:
        raise ItemValidationError(f"{sub_where} が {words} 語です（{low}〜{high} 語）。本文: {text}")

    choices = [str(choice).strip() for choice in raw["choices"]]
    if len(choices) != question_slot.choice_count:
        raise ItemValidationError(
            f"{sub_where}.choices は {question_slot.choice_count} 個必要です（実際: {len(choices)}）"
        )
    clow, chigh = question_slot.choice_words
    for choice_index, choice in enumerate(choices, start=1):
        cwords = len(choice.split())
        if not clow <= cwords <= chigh:
            raise ItemValidationError(
                f"{sub_where}.choices[{choice_index}] が {cwords} 語です（{clow}〜{chigh} 語）。本文: {choice}"
            )

    answer_index = raw.get("answer_index")
    if not isinstance(answer_index, int) or not 0 <= answer_index < len(choices):
        raise ItemValidationError(
            f"{sub_where}: answer_index が範囲外です（0〜{len(choices) - 1}、実際 {answer_index}）"
        )

    return PassageQuestion(
        text=text, choices=choices, answer_index=answer_index, explanation=str(raw["explanation"]).strip()
    )


def passage_to_script(passage_set: PassageSet, listening_format: ListeningFormat) -> DialogueScript:
    """Flatten passage lines + question text into segments. Choices are never spoken —
    real TOEIC Part 3/4 only speaks the passage and the question, not the printed choices."""
    segments: list[DialogueSegment] = []
    for item in passage_set.items:
        for line in item.passage:
            segments.append(
                DialogueSegment(
                    id=f"seg-{len(segments) + 1:03d}",
                    speaker=line.speaker,
                    text=line.text,
                    language=listening_format.language,
                    emotion="Neutral",
                    speed=1.0,
                    pause=0.4,
                    source_section=passage_set.source_id,
                    item_id=item.item_id,
                    role="passage",
                )
            )
        for question in item.questions:
            segments.append(
                DialogueSegment(
                    id=f"seg-{len(segments) + 1:03d}",
                    speaker="narrator",
                    text=question.text,
                    language=listening_format.language,
                    emotion="Neutral",
                    speed=1.0,
                    pause=1.0,
                    source_section=passage_set.source_id,
                    item_id=item.item_id,
                    role="question",
                )
            )
    return DialogueScript(
        title=passage_set.title,
        source_id=passage_set.source_id,
        source_commit=passage_set.source_commit,
        segments=segments,
    )


def passage_to_answers(passage_set: PassageSet) -> dict[str, Any]:
    return {
        "format": passage_set.format_id,
        "title": passage_set.title,
        "source_id": passage_set.source_id,
        "source_commit": passage_set.source_commit,
        "items": [
            {
                "item_id": item.item_id,
                "passage": [{"speaker": line.speaker, "text": line.text} for line in item.passage],
                "questions": [
                    {
                        "question": question.text,
                        "answer_label": _label(question.answer_index),
                        "answer_text": question.choices[question.answer_index],
                        "explanation": question.explanation,
                    }
                    for question in item.questions
                ],
                "reason": item.reason,
            }
            for item in passage_set.items
        ],
    }
