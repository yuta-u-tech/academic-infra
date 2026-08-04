"""TOEIC Part5（空所補充）を acenglish の学習ループへ橋渡しする。

`toeic_reading.render` が印刷用PDFを組むのに使うのと同じ `GrammarItem` を、
ここでは `material` + `generated_item` として取り込む。作問はしない
（Claude が `toeic_reading_cli.py worksheet` の items.json をすでに書いている）。

study-forge の語彙と同様に「1問 = 1 material」にする。セット単位に丸めると
「どの文法項目が身についていないか」が分からなくなるため。
"""

from __future__ import annotations

from typing import Iterator

from ..items import GeneratedItem, GenerationResult, GrammarItem
from .base import ExternalMaterial, note_path_for

SOURCE = "toeic"


def iter_materials(
    set_id: str, items: list[GrammarItem]
) -> Iterator[tuple[ExternalMaterial, GrammarItem]]:
    """1セット分の GrammarItem を「学習対象＋文法問題」の組にする。"""
    for index, item in enumerate(items, start=1):
        review_id = f"toeic.part5.{set_id}.{index:04d}"
        material = ExternalMaterial(
            review_id=review_id,
            source=SOURCE,
            title=f"TOEIC Part5 — {item.point}",
            body=item.sentence,
            origin=set_id,
            source_file=note_path_for("grammar", f"toeic-part5-{set_id}"),
            source_commit=set_id,
        )
        yield material, item


def build_result(material: ExternalMaterial, item: GrammarItem, reason: str) -> GenerationResult:
    return GenerationResult(
        review_id=material.review_id,
        course_id=material.course_id,
        source_commit=material.source_commit,
        generated_by="toeic_reading_cli",
        prompt_version="toeic-reading.part5.1",
        is_ephemeral=False,  # 既に検証されて冊子PDFになった問題なので一時生成物ではない
        items=[GeneratedItem(difficulty=3, reason=reason, item=item)],
    )
