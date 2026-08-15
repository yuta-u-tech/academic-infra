"""Item-centric listening materials.

作問は「1問」を単位に考えるほうが自然なので、Claude には問題の配列を書いてもらう。
そこから音声用の台本・解答・問題冊子を機械的に導く。3つを別々に書かせると必ずズレる。
"""

from __future__ import annotations

import json
from collections import Counter
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
    # 聞き取りの難所(リンキング・リダクション・脱落等)の解説。explanationの文中に
    # 埋め込ませると復習動画・DBから構造化して取り出せないので、別フィールドに分ける
    # (2026-08-12「texなどから発音部分の抽出をして、今度からjsonにも取り入れて」)。
    # 省略可(過去のセットには無い)。
    pronunciation_note: str = ""
    # Part1(写真描写)専用。写真1枚のローカルパス。他の形式では空文字のまま
    # (grouping: flatのitem定義に"question"役割が無い形式=Part1のみ画像を持つ)。
    image_path: str = ""
    # Driveへ公開アップロード後のURL(`listening attach-image-urls`が書き込む)。
    # Forms/PDFへの埋め込みに使う。生成直後のresult.jsonにはまだ無く空文字のまま。
    image_url: str = ""

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


def check_answer_distribution(answer_indexes: list[int], *, min_items: int = 4) -> None:
    """作問側が正解を選択肢の先頭に置く癖への機械的なガード。

    2026-08-15、TOEIC Part1の初回セット(6問)で全問の正解がAのままDrive/YouTube/Formsまで
    公開されてしまった事故を受けて追加。Part5/6/7には作問直後の`shuffle`実行が手順として
    定着していたが、Part1/2/3/4（このListeningSet系）には無かったため、`shuffle-choices`の
    実行漏れを`listening ingest`側で検知して止める。4問未満は判定しない（少数はたまたま
    偏っても実害が小さく、誤検知の方が多くなるため）。
    """
    if len(answer_indexes) < min_items:
        return
    counts = Counter(answer_indexes)
    most_common_index, most_common_count = counts.most_common(1)[0]
    if most_common_count == len(answer_indexes):
        raise ItemValidationError(
            "ANSWER_INDEX_SKEWED: 全"
            f"{len(answer_indexes)}問の正解が選択肢{most_common_index}番目に固定されています。"
            "`listening shuffle-choices --file <result.json> --format <format>` を先に実行して"
            "から ingest をやり直してください。"
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

    if listening_format.id == "toeic-part1" and not raw.get("image_path"):
        raise ItemValidationError(f"{where} に image_path がありません（Part1は写真が必須）。")

    return ListeningItem(
        item_id=str(raw.get("item_id") or f"item-{index:03d}"),
        parts=parts,
        answer_index=answer_index,
        explanation=str(raw["explanation"]).strip(),
        reason=str(raw.get("reason", "")).strip(),
        pronunciation_note=str(raw.get("pronunciation_note", "")).strip(),
        image_path=str(raw.get("image_path", "")).strip(),
        image_url=str(raw.get("image_url", "")).strip(),
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


# 実際の ETS 音源のペーシングに合わせる（Part 2 は質問の後 約1.2秒、次の問題まで 約5秒）。
_PART2_NUMBER_PAUSE = 0.5  # "Number N." の後、質問文が始まる前に置く間（聞き取りやすさのための脚色）
_PART2_QUESTION_PAUSE = 1.2  # 疑問文の後は「本当に尋ねている」間を置く
_PART2_ANSWER_WINDOW = 5.0
_CHOICE_LABELS = ("A", "B", "C", "D")


def to_script(listening_set: ListeningSet, listening_format: ListeningFormat) -> DialogueScript:
    """Flatten items into the segment list the renderer consumes.

    1問につき3つの発話にまとめる（Part1は質問文が存在しないため2つ）:
      1. "Number N."（speaker="narrator"）— 単独の発話にし、直後に短い間を置く。
         質問文と1回の合成にまとめると発話開始直後に質問が始まってしまい、
         「Number N.」を認識する間もなく聞き逃す、という指摘を受けて分離した。
      2. 質問文（speaker="narrator"）。**Part1にはこの発話が無い**（本番同様、写真を見て
         描写文だけを聞く形式。`item.parts_with_role("question")`が空なら省略する）。
      3. 3つ（Part1は4つ）の応答をまとめて1回の合成にする（speaker="respondent"）—
         応答ごとに別々に合成して無音でつなぐと、文と文のつながりの抑揚が失われ棒読みに
         聞こえる。1回の合成にまとめることで Piper 自身の文末ポーズ・抑揚がそのまま活きる。
         各応答の前に "A." "B." "C."（Part1は"D."も）を読み上げる（本番同様、区切りが
         分かるようにする）。
    質問と応答を別の声にするのは、本番より聴き取りやすくするための意図的な脚色
    （本番は全て同じナレーターが読む）。どちらの発話かが声で分かるようにする。
    """
    segments: list[DialogueSegment] = []
    for item_index, item in enumerate(listening_set.items, start=1):
        question_parts = item.parts_with_role("question")
        segments.append(
            DialogueSegment(
                id=f"seg-{len(segments) + 1:03d}",
                speaker="narrator",
                text=f"Number {item_index}.",
                language=listening_format.language,
                emotion="Neutral",
                speed=1.0,
                pause=_PART2_NUMBER_PAUSE,
                source_section=listening_set.source_id,
                item_id=item.item_id,
                role="question",
            )
        )
        if question_parts:
            segments.append(
                DialogueSegment(
                    id=f"seg-{len(segments) + 1:03d}",
                    speaker="narrator",
                    text=question_parts[0].text,
                    language=listening_format.language,
                    emotion="Neutral",
                    speed=1.0,
                    pause=_PART2_QUESTION_PAUSE,
                    source_section=listening_set.source_id,
                    item_id=item.item_id,
                    role="question",
                )
            )
        choices = item.parts_with_role("choice")
        choices_text = " ".join(f"{label}. {choice.text}" for label, choice in zip(_CHOICE_LABELS, choices))
        segments.append(
            DialogueSegment(
                id=f"seg-{len(segments) + 1:03d}",
                speaker="respondent",
                text=choices_text,
                language=listening_format.language,
                emotion="Neutral",
                speed=1.0,
                pause=_PART2_ANSWER_WINDOW,
                source_section=listening_set.source_id,
                item_id=item.item_id,
                role="choice",
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
                "pronunciation_note": item.pronunciation_note,
                "reason": item.reason,
                "image_path": item.image_path or None,
                "image_url": item.image_url or None,
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
    # ListeningItem.pronunciation_note と同じ理由・同じ省略可の扱い。
    pronunciation_note: str = ""


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
        text=text,
        choices=choices,
        answer_index=answer_index,
        explanation=str(raw["explanation"]).strip(),
        pronunciation_note=str(raw.get("pronunciation_note", "")).strip(),
    )


# 実際の ETS 音源: 会話/説明文の前に "Questions X through Y refer to the following ..."、
# 各設問の前に "Number N."。設問の後は答えをマークする時間として約8秒空く。
_PASSAGE_INTRO_PAUSE = 0.5
_PASSAGE_LINE_PAUSE = 0.4
_PASSAGE_NUMBER_PAUSE = 0.5  # "Number N." の後、設問文が始まる前に置く間（聞き取りやすさのための脚色）
_QUESTION_ANSWER_WINDOW = 8.0


def passage_to_script(passage_set: PassageSet, listening_format: ListeningFormat) -> DialogueScript:
    """Flatten passage lines + question text into segments. Choices are never spoken —
    real TOEIC Part 3/4 only speaks the passage and the question, not the printed choices.

    設問番号は冊子側の通し番号（全 item を跨いで連番）と一致させる。
    """
    assert listening_format.passage_slot is not None
    kind = "conversation" if listening_format.passage_slot.speakers > 1 else "talk"
    segments: list[DialogueSegment] = []
    question_number = 0
    for item in passage_set.items:
        start = question_number + 1
        end = question_number + len(item.questions)
        span = f"{start} through {end}" if end > start else str(start)
        segments.append(
            DialogueSegment(
                id=f"seg-{len(segments) + 1:03d}",
                speaker="narrator",
                text=f"Questions {span} refer to the following {kind}.",
                language=listening_format.language,
                emotion="Neutral",
                speed=1.0,
                pause=_PASSAGE_INTRO_PAUSE,
                source_section=passage_set.source_id,
                item_id=item.item_id,
                role="intro",
            )
        )
        for line in item.passage:
            segments.append(
                DialogueSegment(
                    id=f"seg-{len(segments) + 1:03d}",
                    speaker=line.speaker,
                    text=line.text,
                    language=listening_format.language,
                    emotion="Neutral",
                    speed=1.0,
                    pause=_PASSAGE_LINE_PAUSE,
                    source_section=passage_set.source_id,
                    item_id=item.item_id,
                    role="passage",
                )
            )
        for question in item.questions:
            question_number += 1
            # "Number N." は単独の発話にして直後に短い間を置く。設問文と1回の合成に
            # まとめると発話開始直後に設問が始まってしまい、番号を認識する間もなく
            # 聞き逃す、という指摘を受けて分離した（Part 2 の to_script() と同じ理由）。
            segments.append(
                DialogueSegment(
                    id=f"seg-{len(segments) + 1:03d}",
                    speaker="narrator",
                    text=f"Number {question_number}.",
                    language=listening_format.language,
                    emotion="Neutral",
                    speed=1.0,
                    pause=_PASSAGE_NUMBER_PAUSE,
                    source_section=passage_set.source_id,
                    item_id=item.item_id,
                    role="question",
                )
            )
            # 設問の後の8秒はマーク時間そのもの＝「本当に尋ねている」間として十分機能する。
            segments.append(
                DialogueSegment(
                    id=f"seg-{len(segments) + 1:03d}",
                    speaker="narrator",
                    text=question.text,
                    language=listening_format.language,
                    emotion="Neutral",
                    speed=1.0,
                    pause=_QUESTION_ANSWER_WINDOW,
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


_GENERIC_CHOICE_LABELS = ("A", "B", "C", "D")


def to_form_items(
    listening_set: ListeningSet, listening_format: ListeningFormat, set_id: str
) -> list[dict[str, Any]]:
    """review_id 提出用フォーム(toeic_forms_cli.py create)向けのフラットな選択式項目に変換する。

    `answer_in_audio` が True の形式（TOEIC Part 2）は、設問・選択肢の実テキストが
    音声でしか聞けない出題方式そのもの（冊子も空欄のみ、`render_tex` を見よ）。
    Form にテキストを見せると音声を聴かずに答えられてしまい出題方式が壊れるため、
    "Number N." と A/B/C の記号だけを持つ固定テンプレートにする
    （2026-08-10、Form にテキストが出ているとユーザー指摘を受けて修正。
    最初の修正版で選択肢テキストの二重表示は直したが、そもそも Part 2 は
    テキストを一切見せてはいけない形式だという点を見落としていた）。
    それ以外（Part 3/4、answer_in_audio=False）は選択肢が冊子にも印刷される形式なので
    実テキストをそのまま使う。
    """
    part_slug = listening_set.format_id.removeprefix("toeic-")
    items: list[dict[str, Any]] = []
    for index, item in enumerate(listening_set.items, start=1):
        choice_parts = item.parts_with_role("choice")
        if listening_format.answer_in_audio:
            question_title = f"Number {index}."
            choices = list(_GENERIC_CHOICE_LABELS[: len(choice_parts)])
        else:
            question_text = item.parts_with_role("question")[0].text
            question_title = f"Number {index}. {question_text}"
            choices = [choice_part.text for choice_part in choice_parts]
        form_item = {
            "kind": "choice",
            "review_id": f"toeic.listening.{part_slug}.{set_id}.{index:04d}",
            "topic": listening_set.format_id,
            "difficulty": 3,
            "question": question_title,
            "choices": choices,
            "answer_index": item.answer_index,
            "explanation": item.explanation,
        }
        if item.image_url:
            # Part1(写真描写)は写真を見ながら解く形式なので、Formsにも画像を出す
            # (`listening attach-image-urls`で事前にDriveへ公開アップロード済みのURL)。
            form_item["image_url"] = item.image_url
        items.append(form_item)
    return items


def passage_to_form_items(passage_set: PassageSet, set_id: str) -> list[dict[str, Any]]:
    """review_id 提出用フォーム(toeic_forms_cli.py create)向けの選択式項目に変換する（Part3/4）。

    title には passage（会話/説明文の書き起こし）+ 設問文だけを置く。選択肢は choices として
    別に渡すので、title に選択肢テキストを重ねて書かない（to_form_items と同じ理由）。
    """
    part_slug = passage_set.format_id.removeprefix("toeic-")
    items: list[dict[str, Any]] = []
    for item_index, item in enumerate(passage_set.items, start=1):
        passage_text = " / ".join(f"{line.speaker}: {line.text}" for line in item.passage)
        for question_index, question in enumerate(item.questions, start=1):
            items.append(
                {
                    "kind": "choice",
                    "review_id": f"toeic.listening.{part_slug}.{set_id}.{item_index:04d}.{question_index}",
                    "topic": passage_set.format_id,
                    "difficulty": 3,
                    "question": f"{passage_text} // {question.text}",
                    "choices": question.choices,
                    "answer_index": question.answer_index,
                    "explanation": question.explanation,
                }
            )
    return items


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
                        "pronunciation_note": question.pronunciation_note,
                    }
                    for question in item.questions
                ],
                "reason": item.reason,
            }
            for item in passage_set.items
        ],
    }
