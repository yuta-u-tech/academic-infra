"""study-forge の TOEIC 語彙デッキを取り込む。

`yuta-u-tech/study-forge` の `data/*.json` には `{term, definition, example}` が既に
揃っているので、**ここだけは Claude の生成を通さない**。語義も例文も人手で用意された
ものがあるのに、それを捨てて生成し直す理由がない。

    terms: [{"term": "anyway", "definition": "とにかく",
             "example": "何事も…例: Anyway, let's try.（とにかくやってみよう）"}]

1語 = 1 material にする。デッキ単位にすると 981 語が1つの習熟度に丸められて、
「どの語が身についていないか」が分からなくなるため。

出典は市販の単語集に由来する。取り込み先は `~/.academic-english/english.db`（ローカル）
と private なノートまでで、**public な academic-infra には書かない**。
"""

from __future__ import annotations

import json
import urllib.request
from typing import Iterator

from ..items import GeneratedItem, GenerationResult, VocabItem
from .base import ExternalMaterial, note_path_for, slugify

REPOSITORY = "yuta-u-tech/study-forge"
_RAW_BASE = f"https://raw.githubusercontent.com/{REPOSITORY}/HEAD/data"
_TIMEOUT_SECONDS = 30

DECKS = (
    "words1-400",
    "words401-700",
    "words701-900",
    "words901-1000",
    "supplement1",
    "supplement2",
    "supplement3",
)


class DeckNotFoundError(Exception):
    pass


def fetch_deck(deck: str, timeout: int = _TIMEOUT_SECONDS) -> dict:
    if deck not in DECKS:
        raise DeckNotFoundError(f"未知のデッキ '{deck}'（対応: {', '.join(DECKS)}）")
    request = urllib.request.Request(
        f"{_RAW_BASE}/{deck}.json", headers={"User-Agent": "acenglish/1.0"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - 固定のhttps
        return json.loads(response.read().decode("utf-8"))


def split_example(raw: str) -> tuple[str | None, str | None]:
    """study-forge の example は「解説。例: <英文>（<訳>）」という1本の文字列。

    英文だけを取り出せると、そのまま英語の例文として使える。取り出せない形式なら
    無理に切らずに諦める（壊れた英文を教材に混ぜるより、例文なしの方がまし）。
    """
    if not raw:
        return None, None
    _, separator, tail = raw.partition("例:")
    if not separator:
        return None, raw.strip() or None
    english, _, japanese = tail.partition("（")
    return english.strip() or None, japanese.rstrip("）").strip() or None


def iter_materials(deck: str, terms: list[dict]) -> Iterator[tuple[ExternalMaterial, VocabItem]]:
    """デッキの各語を「学習対象＋語彙カード」の組にする。"""
    for index, entry in enumerate(terms, start=1):
        term = (entry.get("term") or "").strip()
        definition = (entry.get("definition") or "").strip()
        if not term or not definition:
            continue

        english_example, japanese_gloss = split_example(entry.get("example") or "")
        review_id = f"toeic.{deck}.{index:04d}"
        material = ExternalMaterial(
            review_id=review_id,
            source="toeic",
            title=term,
            body=f"{term}\n{definition}\n{entry.get('example', '')}".strip(),
            origin=f"{REPOSITORY}:data/{deck}.json#{index}",
            source_file=note_path_for("vocabulary", f"toeic-{deck}"),
            source_commit=deck,
            chapter_title=deck,
        )
        item = VocabItem(
            sub_skill="recall",
            word=term,
            meaning=definition,
            example=english_example,
            collocations=[],
        )
        yield material, item


def build_result(material: ExternalMaterial, item: VocabItem, note: str) -> GenerationResult:
    """語彙カード1枚分の取り込み単位。生成物と同じ器に載せて出所を残す。"""
    return GenerationResult(
        review_id=material.review_id,
        course_id=material.course_id,
        source_commit=material.source_commit,
        generated_by=f"studyforge:{REPOSITORY}",
        prompt_version="import-1",
        is_ephemeral=False,  # 人手で用意された語義・例文なので一時生成物ではない
        items=[GeneratedItem(difficulty=3, reason=note, item=item)],
    )


def deck_slug(deck: str) -> str:
    return slugify(f"toeic-{deck}")
