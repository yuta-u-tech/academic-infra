"""TOEICリスニング（Part2/3/4）を acenglish の学習ループへ橋渡しする。

`toeic_part5.py`/`toeic_part7.py` と同じ役割。音声そのものはこのDBに複製しない
（正本は academic-english-data / YouTube）。printed 冊子には設問文が出ない場合がある
（Part2の `answer_in_audio`）が、`result.json`（`academic_audio.items.load_result`/
`load_passage_result` が返す型）自体には質問・選択肢のテキストが入っているので、
そこから学習ループ用の `ListeningItem` を作る。

Part2（grouping: item）は `toeic_part5.py` と同じく設問1つ=review_id 1つ。
Part3/4（grouping: passage）は `toeic_part7.py` と同じく
`toeic.listening.<part>.<set_id>.<passage連番>.<設問連番>` で設問ごとに分ける。
"""

from __future__ import annotations

from typing import Iterator

from academic_audio.items import ListeningSet, PassageSet

from ..items import GeneratedItem, GenerationResult, ListeningItem
from .base import ExternalMaterial, note_path_for

SOURCE = "toeic"


def iter_materials(
    set_id: str, listening_set: ListeningSet, part: str
) -> Iterator[tuple[ExternalMaterial, ListeningItem]]:
    """grouping: item（Part2）の設問を「学習対象＋リスニング問題」の組にする。"""
    for index, item in enumerate(listening_set.items, start=1):
        if item.answer_index is None:
            continue  # 正解の無い設問は学習ループの対象外
        review_id = f"toeic.listening.{part}.{set_id}.{index:04d}"
        questions = item.parts_with_role("question")
        choices = [choice.text for choice in item.parts_with_role("choice")]
        question_text = questions[0].text if questions else "(音声のみ。設問文は台本を参照)"
        material = ExternalMaterial(
            review_id=review_id,
            source=SOURCE,
            title=f"TOEIC {listening_set.format_id} — item {index}",
            body=question_text,
            origin=set_id,
            source_file=note_path_for("listening", f"toeic-{part}-{set_id}"),
            source_commit=set_id,
        )
        listening_item = ListeningItem(
            sub_skill=part,
            question=question_text,
            choices=choices,
            answer_index=item.answer_index,
            explanation=item.explanation,
            pronunciation_note=item.pronunciation_note or None,
        )
        yield material, listening_item


def iter_materials_passage(
    set_id: str, passage_set: PassageSet, part: str
) -> Iterator[tuple[ExternalMaterial, ListeningItem]]:
    """grouping: passage（Part3/4）の設問を展開する。"""
    for passage_index, item in enumerate(passage_set.items, start=1):
        for question_index, question in enumerate(item.questions, start=1):
            review_id = f"toeic.listening.{part}.{set_id}.{passage_index:04d}.{question_index}"
            material = ExternalMaterial(
                review_id=review_id,
                source=SOURCE,
                title=f"TOEIC {passage_set.format_id} — passage {passage_index} Q{question_index}",
                body=question.text,
                origin=set_id,
                source_file=note_path_for("listening", f"toeic-{part}-{set_id}"),
                source_commit=set_id,
            )
            listening_item = ListeningItem(
                sub_skill=part,
                question=question.text,
                choices=question.choices,
                answer_index=question.answer_index,
                explanation=question.explanation,
                pronunciation_note=question.pronunciation_note or None,
            )
            yield material, listening_item


def build_result(material: ExternalMaterial, item: ListeningItem, reason: str) -> GenerationResult:
    return GenerationResult(
        review_id=material.review_id,
        course_id=material.course_id,
        source_commit=material.source_commit,
        generated_by="academic_audio_cli",
        prompt_version="toeic-listening.1",
        is_ephemeral=False,  # 既に検証されて音声・冊子になった問題なので一時生成物ではない
        items=[GeneratedItem(difficulty=3, reason=reason, item=item)],
    )
