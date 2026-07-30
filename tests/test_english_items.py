"""生成物スキーマ: 壊れた生成物を DB に入れる前に落とす。"""

import pytest
from pydantic import ValidationError

from acenglish.items import GenerationResult, ReadingItem, VocabItem, write_json_schemas


def result_payload(**item_overrides) -> dict:
    item = {
        "kind": "reading",
        "passage": "A binary search tree keeps its keys in sorted order.",
        "question": "What does the passage state?",
        "choices": ["Keys are sorted.", "Keys are random."],
        "answer_index": 0,
        "explanation": "The first sentence says so.",
    }
    item.update(item_overrides)
    return {
        "review_id": "dsa.ch02.list.s01",
        "course_id": "dsa",
        "source_commit": "abc123",
        "generated_by": "claude-opus-5",
        "prompt_version": "2026-07-30.1",
        "items": [{"difficulty": 3, "reason": "中心概念のため", "item": item}],
    }


def test_a_valid_result_parses():
    result = GenerationResult.model_validate(result_payload())
    assert result.items[0].item.kind == "reading"
    assert result.is_ephemeral is True


def test_answer_index_outside_the_choices_is_rejected():
    with pytest.raises(ValidationError, match="範囲外"):
        GenerationResult.model_validate(result_payload(answer_index=5))


def test_a_single_choice_question_is_rejected():
    with pytest.raises(ValidationError):
        GenerationResult.model_validate(result_payload(choices=["only one"]))


def test_unknown_fields_are_rejected():
    """生成が余計なキーを吐いたら黙って捨てず、その場で気づけるようにする。"""
    with pytest.raises(ValidationError):
        GenerationResult.model_validate(result_payload(hallucinated_field="x"))


def test_provenance_is_mandatory():
    payload = result_payload()
    del payload["source_commit"]
    with pytest.raises(ValidationError):
        GenerationResult.model_validate(payload)


def test_reading_answers_are_checked_by_index():
    item = ReadingItem.model_validate(result_payload()["items"][0]["item"])
    assert item.check("0") is True
    assert item.check("1") is False
    assert item.check("") is False


def test_vocab_answers_ignore_case_and_padding():
    item = VocabItem(word="Sentinel Node", meaning="番兵ノード")
    assert item.check("  sentinel node ") is True
    assert item.check("sentinel") is False


def test_json_schema_is_written_for_humans_and_agents(tmp_path):
    paths = write_json_schemas(tmp_path)
    assert paths and paths[0].exists()
    assert "review_id" in paths[0].read_text(encoding="utf-8")
