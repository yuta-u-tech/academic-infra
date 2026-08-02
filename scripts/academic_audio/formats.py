"""Declarative listening formats.

試験形式をコードに埋めると、別の試験を足すたびに書き直しになる。形式は
`audio/formats/*.md` に 1形式 1ファイルで置き、front matter に機械可読の制約、
本文に作問方針を書く。両方を同じファイルに置くのは、片方だけ直してズレるのを防ぐため。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

FORMAT_DIR = Path(__file__).resolve().parent.parent.parent / "audio" / "formats"


class FormatError(Exception):
    pass


@dataclass(frozen=True)
class ItemSlot:
    """1問の中に現れる発話の枠（grouping: flat の形式で使う）。"""

    role: str
    count: int = 1
    words: tuple[int, int] | None = None
    pause: float = 0.5


@dataclass(frozen=True)
class PassageSlot:
    """1問＝1つの音声（会話・説明文）の制約（grouping: passage の形式で使う）。"""

    speakers: int
    turns: tuple[int, int]
    words_per_turn: tuple[int, int]


@dataclass(frozen=True)
class QuestionSlot:
    """passage に続く設問の制約（grouping: passage の形式で使う）。"""

    count: int
    words: tuple[int, int]
    choice_count: int
    choice_words: tuple[int, int]


@dataclass(frozen=True)
class ListeningFormat:
    id: str
    name: str
    engine: str
    language: str
    speakers: int
    answer_in_audio: bool
    grouping: str  # "flat"（1問=1発話群、TOEIC Part 2 等） | "passage"（1問=1音声+複数設問、Part 3/4）
    item: list[ItemSlot]  # grouping: flat のみ。grouping: passage では空
    passage_slot: PassageSlot | None  # grouping: passage のみ
    question_slot: QuestionSlot | None  # grouping: passage のみ
    guidance: str
    path: Path

    @property
    def segments_per_item(self) -> int:
        return sum(slot.count for slot in self.item)

    def slot_for(self, role: str) -> ItemSlot | None:
        return next((slot for slot in self.item if slot.role == role), None)

    @property
    def choice_count(self) -> int:
        slot = self.slot_for("choice")
        return slot.count if slot else 0


def available_formats(directory: Path = FORMAT_DIR) -> list[str]:
    if not directory.is_dir():
        return []
    return sorted(path.stem for path in directory.glob("*.md"))


def load_format(format_id: str, directory: Path = FORMAT_DIR) -> ListeningFormat:
    path = directory / f"{format_id}.md"
    if not path.exists():
        known = ", ".join(available_formats(directory)) or "（なし）"
        raise FormatError(f"形式 '{format_id}' がありません。{path} を作ってください。使えるのは: {known}")
    front_matter, guidance = _split_front_matter(path)
    return _build_format(front_matter, guidance, path)


def _split_front_matter(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise FormatError(f"{path} に front matter がありません。")
    end = text.find("\n---", 3)
    if end == -1:
        raise FormatError(f"{path} の front matter が閉じていません。")
    try:
        front_matter = yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError as error:
        raise FormatError(f"{path} の front matter を読めません: {error}") from error
    if not isinstance(front_matter, dict):
        raise FormatError(f"{path} の front matter がマッピングではありません。")
    return front_matter, text[end + 4 :].strip()


def _build_format(front_matter: dict, guidance: str, path: Path) -> ListeningFormat:
    for key in ("id", "name", "engine", "language"):
        if key not in front_matter:
            raise FormatError(f"{path} の front matter に {key} がありません。")
    if front_matter["id"] != path.stem:
        raise FormatError(f"{path}: front matter の id '{front_matter['id']}' がファイル名と違います。")

    grouping = front_matter.get("grouping", "flat")
    if grouping not in ("flat", "passage"):
        raise FormatError(f"{path}: grouping は flat か passage です（実際: {grouping}）")

    if grouping == "flat":
        if "item" not in front_matter:
            raise FormatError(f"{path} の front matter に item がありません。")
        slots = [_build_slot(raw, path, index) for index, raw in enumerate(front_matter["item"], start=1)]
        if not slots:
            raise FormatError(f"{path}: item が空です。")
        passage_slot: PassageSlot | None = None
        question_slot: QuestionSlot | None = None
    else:
        for key in ("passage", "questions"):
            if key not in front_matter:
                raise FormatError(f"{path}: grouping: passage には front matter に {key} が必要です。")
        slots = []
        passage_slot = _build_passage_slot(front_matter["passage"], path)
        question_slot = _build_question_slot(front_matter["questions"], path)

    return ListeningFormat(
        id=front_matter["id"],
        name=front_matter["name"],
        engine=front_matter["engine"],
        language=front_matter["language"],
        speakers=int(front_matter.get("speakers", 1)),
        answer_in_audio=bool(front_matter.get("answer_in_audio", False)),
        grouping=grouping,
        item=slots,
        passage_slot=passage_slot,
        question_slot=question_slot,
        guidance=guidance,
        path=path,
    )


def _build_slot(raw: object, path: Path, index: int) -> ItemSlot:
    if not isinstance(raw, dict) or "role" not in raw:
        raise FormatError(f"{path}: item[{index}] に role がありません。")
    words = raw.get("words")
    if words is not None:
        words = _pair(words, path, f"item[{index}].words")
    return ItemSlot(
        role=str(raw["role"]),
        count=int(raw.get("count", 1)),
        words=words,
        pause=float(raw.get("pause", 0.5)),
    )


def _build_passage_slot(raw: object, path: Path) -> PassageSlot:
    if not isinstance(raw, dict):
        raise FormatError(f"{path}: passage がマッピングではありません。")
    for key in ("speakers", "turns", "words_per_turn"):
        if key not in raw:
            raise FormatError(f"{path}: passage.{key} がありません。")
    return PassageSlot(
        speakers=int(raw["speakers"]),
        turns=_pair(raw["turns"], path, "passage.turns"),
        words_per_turn=_pair(raw["words_per_turn"], path, "passage.words_per_turn"),
    )


def _build_question_slot(raw: object, path: Path) -> QuestionSlot:
    if not isinstance(raw, dict):
        raise FormatError(f"{path}: questions がマッピングではありません。")
    for key in ("count", "words", "choice_count", "choice_words"):
        if key not in raw:
            raise FormatError(f"{path}: questions.{key} がありません。")
    return QuestionSlot(
        count=int(raw["count"]),
        words=_pair(raw["words"], path, "questions.words"),
        choice_count=int(raw["choice_count"]),
        choice_words=_pair(raw["choice_words"], path, "questions.choice_words"),
    )


def _pair(value: object, path: Path, name: str) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2:
        raise FormatError(f"{path}: {name} は [最小, 最大] で書いてください。")
    return (int(value[0]), int(value[1]))
