"""Item-centric listening materials.

作問は「1問」を単位に考えるほうが自然なので、Claude には問題の配列を書いてもらう。
そこから音声用の台本・解答・問題冊子を機械的に導く。3つを別々に書かせると必ずズレる。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .formats import ListeningFormat
from .models import DialogueScript, DialogueSegment


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
