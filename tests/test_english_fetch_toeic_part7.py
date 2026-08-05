"""TOEIC Part7 の passages を acenglish の学習ループへ取り込む（通信はしない）。"""

from acenglish.db import connect
from acenglish.fetch import import_toeic_part7
from acenglish.sources.toeic_part7 import Part7Passage


def _passage(n_questions: int = 2) -> Part7Passage:
    return Part7Passage.model_validate(
        {
            "passage": "Dear Team, the meeting has been moved to 3 PM.",
            "passage_type": "single",
            "questions": [
                {
                    "question": f"Question {i}?",
                    "choices": ["A", "B", "C", "D"],
                    "answer_index": 0,
                    "explanation": "説明。",
                    "sub_skill": "comprehension",
                }
                for i in range(n_questions)
            ],
        }
    )


def test_import_creates_one_material_and_generated_item_per_question(tmp_path):
    passages = [_passage(2)]
    with connect(tmp_path / "english.db") as connection:
        imported = import_toeic_part7(connection, "20260805", passages)
        assert imported == 2

        materials = connection.execute("SELECT review_id, source FROM material ORDER BY review_id").fetchall()
        assert [dict(row) for row in materials] == [
            {"review_id": "toeic.part7.20260805.0001.1", "source": "toeic"},
            {"review_id": "toeic.part7.20260805.0001.2", "source": "toeic"},
        ]

        generated = connection.execute(
            "SELECT COUNT(*) AS n FROM generated_item WHERE kind = 'reading'"
        ).fetchone()["n"]
        assert generated == 2


def test_multiple_passages_get_distinct_passage_indices(tmp_path):
    passages = [_passage(1), _passage(2)]
    with connect(tmp_path / "english.db") as connection:
        imported = import_toeic_part7(connection, "20260805", passages)
        assert imported == 3

        review_ids = [
            row["review_id"]
            for row in connection.execute("SELECT review_id FROM material ORDER BY review_id")
        ]
        assert review_ids == [
            "toeic.part7.20260805.0001.1",
            "toeic.part7.20260805.0002.1",
            "toeic.part7.20260805.0002.2",
        ]


def test_import_is_idempotent(tmp_path):
    passages = [_passage(1)]
    with connect(tmp_path / "english.db") as connection:
        first = import_toeic_part7(connection, "20260805", passages)
        second = import_toeic_part7(connection, "20260805", passages)

    assert first == 1
    assert second == 0
