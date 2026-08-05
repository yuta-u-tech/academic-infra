"""Part7の items.json（passagesグルーピング形）読み込み・バリデーション。"""

import json

import pytest

from acenglish.sources.toeic_part7 import load_part7_items


def _valid_payload() -> dict:
    return {
        "title": "Part7 テスト",
        "passages": [
            {
                "passage": "Dear Team, the meeting has been moved to 3 PM.",
                "passage_type": "single",
                "questions": [
                    {
                        "question": "What time is the meeting now?",
                        "choices": ["1 PM", "2 PM", "3 PM", "4 PM"],
                        "answer_index": 2,
                        "explanation": "本文に3 PMと明記されている。",
                        "sub_skill": "comprehension",
                    }
                ],
            }
        ],
    }


def test_a_valid_payload_loads_correctly(tmp_path):
    path = tmp_path / "items.json"
    path.write_text(json.dumps(_valid_payload()), encoding="utf-8")

    title, passages = load_part7_items(path)

    assert title == "Part7 テスト"
    assert len(passages) == 1
    assert passages[0].passage_type == "single"
    assert len(passages[0].questions) == 1
    assert passages[0].questions[0].answer_index == 2


def test_missing_passages_key_is_a_clear_error(tmp_path):
    path = tmp_path / "items.json"
    path.write_text(json.dumps({"title": "x"}), encoding="utf-8")

    with pytest.raises(SystemExit):
        load_part7_items(path)


def test_empty_passages_is_rejected(tmp_path):
    path = tmp_path / "items.json"
    path.write_text(json.dumps({"title": "x", "passages": []}), encoding="utf-8")

    with pytest.raises(SystemExit):
        load_part7_items(path)


def test_a_passage_needs_at_least_one_question(tmp_path):
    payload = _valid_payload()
    payload["passages"][0]["questions"] = []
    path = tmp_path / "items.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SystemExit):
        load_part7_items(path)
