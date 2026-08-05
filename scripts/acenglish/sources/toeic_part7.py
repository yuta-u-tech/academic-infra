"""TOEIC Part7（読解）を acenglish の学習ループへ橋渡しする。

`toeic_part5.py` と同じ役割だが、Part7は1つのpassageに複数の設問がぶら下がる点が違う。
`generated_item` の重複防止チェックが `review_id + kind` の存在有無だけなので、
passage単位でreview_idをまとめてしまうと2問目以降が二重登録されないまま失われる。
そのため **設問1つ = review_id 1つ**（`toeic.part7.<set_id>.<passage連番>.<設問連番>`）を
Part5と同じ方針で維持し、passageのグルーピングはitems.json側の入力構造と冊子レンダリング
だけで扱う（DBには反映しない）。

Claude入力用の `Part7Passage`/`Part7Question`（items.jsonのpassagesグルーピング形）も
ここに置く。`toeic_reading/render.py`・`toeic_reading_cli.py` はこのモジュールから型を
読みに行く（`render.py`が`acenglish.items`から`GrammarItem`を読むのと同じ向き）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, Literal

from pydantic import BaseModel, Field, ValidationError

from ..items import GeneratedItem, GenerationResult, ReadingItem
from .base import ExternalMaterial, note_path_for

SOURCE = "toeic"


class Part7Question(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    choices: list[str] = Field(min_length=2, max_length=6)
    answer_index: int = Field(ge=0)
    explanation: str = Field(min_length=1, max_length=2000)
    sub_skill: Literal["comprehension", "syntax_parsing", "vocabulary", "reading_speed"] = (
        "comprehension"
    )


class Part7Passage(BaseModel):
    passage: str = Field(min_length=1, max_length=4000)
    passage_type: Literal["single", "double", "triple"] = "single"
    questions: list[Part7Question] = Field(min_length=1)


def load_part7_items(path: Path) -> tuple[str, list[Part7Passage]]:
    """items.json（`{title, passages: [...]}`）を検証して読む。

    形式が不正なら他のCLIコマンドと同じくSystemExitで分かりやすく落とす。
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    title = payload.get("title") or "Part7"
    try:
        passages = [Part7Passage.model_validate(entry) for entry in payload["passages"]]
    except (KeyError, ValidationError) as error:
        raise SystemExit(f"passages の形式が不正です:\n{error}")
    if not passages:
        raise SystemExit("passages が空です。")
    return title, passages


def iter_materials(
    set_id: str, passages: list[Part7Passage]
) -> Iterator[tuple[ExternalMaterial, ReadingItem]]:
    """passageごとの設問を「学習対象＋読解問題」の組に展開する。"""
    for passage_index, passage in enumerate(passages, start=1):
        for question_index, question in enumerate(passage.questions, start=1):
            review_id = f"toeic.part7.{set_id}.{passage_index:04d}.{question_index}"
            material = ExternalMaterial(
                review_id=review_id,
                source=SOURCE,
                title=f"TOEIC Part7 — passage {passage_index} Q{question_index}",
                body=passage.passage,
                origin=set_id,
                source_file=note_path_for("reading", f"toeic-part7-{set_id}"),
                source_commit=set_id,
            )
            item = ReadingItem(
                sub_skill=question.sub_skill,
                passage=passage.passage,
                question=question.question,
                choices=question.choices,
                answer_index=question.answer_index,
                explanation=question.explanation,
            )
            yield material, item


def build_result(material: ExternalMaterial, item: ReadingItem, reason: str) -> GenerationResult:
    return GenerationResult(
        review_id=material.review_id,
        course_id=material.course_id,
        source_commit=material.source_commit,
        generated_by="toeic_reading_cli",
        prompt_version="toeic-reading.part7.1",
        is_ephemeral=False,  # 既に検証されて冊子PDFになった問題なので一時生成物ではない
        items=[GeneratedItem(difficulty=3, reason=reason, item=item)],
    )
