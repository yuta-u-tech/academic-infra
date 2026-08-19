"""個人のTeX単語ノート（`\\card{語}{品詞}{意味}{例文}` マクロ形式）を取り込む。

studyforge.py と同じ「既に語義・例文が人手で用意されている」ケースなので生成は挟まない。
出典が市販の単語集ではなく本人の手書きノートである点だけが違う。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

from ..items import GeneratedItem, GenerationResult, VocabItem
from .base import ExternalMaterial, note_path_for

SOURCE_PREFIX = "personal-notes"

# \card{見出し語}{品詞}{意味}{例文} を balanced-brace で読む。
# 見出し語・意味の中に \textasciitilde{} のようなネストした {} が
# 混ざるノートが実在するため、正規表現の非貪欲マッチでは壊れる（2026-08-19確認）。
_CARD_START = re.compile(r"\\card\{")


def _read_balanced_arg(text: str, start: int) -> tuple[str, int]:
    """text[start] が '{' である前提で、対応する '}' までを balanced に読む。

    戻り値は (中身, '}' の次の位置)。
    """
    assert text[start] == "{"
    depth = 0
    i = start
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:i], i + 1
        i += 1
    raise ValueError(f"'{{' に対応する '}}' が見つかりません（位置 {start}）。")


def parse_cards(tex: str) -> list[tuple[str, str, str, str]]:
    """(word, part_of_speech, meaning, example) のリストを返す（出現順）。"""
    cards: list[tuple[str, str, str, str]] = []
    for match in _CARD_START.finditer(tex):
        pos = match.end() - 1  # '{' の位置
        args = []
        for _ in range(4):
            if pos >= len(tex) or tex[pos] != "{":
                break
            value, pos = _read_balanced_arg(tex, pos)
            args.append(value.strip())
        if len(args) == 4:
            cards.append(tuple(args))  # type: ignore[arg-type]
    return cards


def iter_materials(
    path: Path, cards: list[tuple[str, str, str, str]], known_words: set[str],
) -> Iterator[tuple[ExternalMaterial, VocabItem]]:
    """`known_words`（casefold済み）に無い語だけを取り込み対象として返す。"""
    seen_in_file: set[str] = set()
    index = 0
    for word, part_of_speech, meaning, example in cards:
        key = word.strip().casefold()
        if not word or not meaning:
            continue
        if key in known_words or key in seen_in_file:
            continue
        seen_in_file.add(key)
        index += 1
        review_id = f"toeic.{SOURCE_PREFIX}.{index:04d}"
        material = ExternalMaterial(
            review_id=review_id,
            source="toeic",
            title=word,
            body=f"{word}\n{meaning}\n{example}".strip(),
            origin=f"local-tex:{path.name}#{index}",
            source_file=note_path_for("vocabulary", SOURCE_PREFIX),
            source_commit=SOURCE_PREFIX,
            chapter_title=SOURCE_PREFIX,
        )
        item = VocabItem(
            sub_skill="recall",
            word=word,
            meaning=meaning,
            example=example or None,
            part_of_speech=part_of_speech or None,
            collocations=[],
        )
        yield material, item


def build_result(material: ExternalMaterial, item: VocabItem, note: str) -> GenerationResult:
    return GenerationResult(
        review_id=material.review_id,
        course_id=material.course_id,
        source_commit=material.source_commit,
        generated_by="import:personal-notes-tex",
        prompt_version="import-1",
        is_ephemeral=False,
        items=[GeneratedItem(difficulty=3, reason=note, item=item)],
    )
