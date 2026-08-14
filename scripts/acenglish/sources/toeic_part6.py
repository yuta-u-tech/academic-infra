"""TOEIC Part6（長文穴埋め）を acenglish の学習ループへ橋渡しする。

`toeic_part7.py` と同じ役割（1つのpassageに複数の設問がぶら下がる）だが、Part6は
Part5と同じ「空所補充＋point/pattern追跡」を1passage内の4設問すべてに持たせる点が違う。
`toeic_part5.py`のGrammarItemと`toeic_part7.py`のReadingItem/Part7Passageを合成した形。

Claude入力用の `Part6Passage`/`Part6Question`（items.jsonのpassagesグルーピング形）も
ここに置く。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, Literal

from pydantic import BaseModel, Field, ValidationError

from ..items import GeneratedItem, GenerationResult, ReadingBlankItem
from .base import ExternalMaterial, note_path_for

SOURCE = "toeic"


class Part6Question(BaseModel):
    blank_number: int = Field(ge=1, le=4)
    blank_type: Literal["word", "sentence"] = "word"
    choices: list[str] = Field(min_length=3, max_length=5)
    answer_index: int = Field(ge=0)
    explanation: str = Field(min_length=1, max_length=2000)
    point: str = Field(min_length=1, max_length=120)
    pattern: Literal["A", "B", "C"] | None = None
    pattern_note: str | None = None


class Part6Passage(BaseModel):
    passage: str = Field(min_length=1, max_length=4000, description="空所は [1]〜[4] で示す")
    passage_type: Literal["email", "memo", "notice", "advertisement", "article"] = "email"
    questions: list[Part6Question] = Field(min_length=4, max_length=4)


def load_part6_items(path: Path) -> tuple[str, list[Part6Passage]]:
    """items.json（`{title, passages: [...]}`）を検証して読む。"""
    payload = json.loads(path.read_text(encoding="utf-8"))
    title = payload.get("title") or "Part6"
    try:
        passages = [Part6Passage.model_validate(entry) for entry in payload["passages"]]
    except (KeyError, ValidationError) as error:
        raise SystemExit(f"passages の形式が不正です:\n{error}")
    if not passages:
        raise SystemExit("passages が空です。")
    return title, passages


def iter_materials(
    set_id: str, passages: list[Part6Passage]
) -> Iterator[tuple[ExternalMaterial, ReadingBlankItem]]:
    """passageごとの設問(空所)を「学習対象＋空所補充問題」の組に展開する。"""
    for passage_index, passage in enumerate(passages, start=1):
        for question in passage.questions:
            review_id = f"toeic.part6.{set_id}.{passage_index:04d}.{question.blank_number}"
            material = ExternalMaterial(
                review_id=review_id,
                source=SOURCE,
                title=f"TOEIC Part6 — passage {passage_index} blank[{question.blank_number}]",
                body=passage.passage,
                origin=set_id,
                source_file=note_path_for("reading", f"toeic-part6-{set_id}"),
                source_commit=set_id,
            )
            item = ReadingBlankItem(
                passage=passage.passage,
                blank_number=question.blank_number,
                blank_type=question.blank_type,
                choices=question.choices,
                answer_index=question.answer_index,
                explanation=question.explanation,
                point=question.point,
                pattern=question.pattern,
                pattern_note=question.pattern_note,
            )
            yield material, item


def build_result(material: ExternalMaterial, item: ReadingBlankItem, reason: str) -> GenerationResult:
    return GenerationResult(
        review_id=material.review_id,
        course_id=material.course_id,
        source_commit=material.source_commit,
        generated_by="toeic_reading_cli",
        prompt_version="toeic-reading.part6.1",
        is_ephemeral=False,
        items=[GeneratedItem(difficulty=3, reason=reason, item=item)],
    )
