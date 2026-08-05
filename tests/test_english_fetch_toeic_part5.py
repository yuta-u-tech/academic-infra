"""TOEIC Part5 の items を acenglish の学習ループへ取り込む（通信はしない）。"""

from acenglish.db import connect
from acenglish.fetch import import_toeic_part5
from acenglish.items import GrammarItem


def _grammar_item(point: str) -> GrammarItem:
    return GrammarItem(
        sentence="The manager ____ the report yesterday.",
        choices=["submit", "submits", "submitted", "submitting"],
        answer_index=2,
        explanation="過去の出来事なので過去形。",
        point=point,
        pattern="A",
        pattern_note="同じ語(submit)の語形違いのみで構成しているため。",
    )


def test_import_creates_one_material_and_generated_item_per_question(tmp_path):
    items = [_grammar_item("時制"), _grammar_item("態")]
    with connect(tmp_path / "english.db") as connection:
        imported = import_toeic_part5(connection, "20260804", items)
        assert imported == 2

        materials = connection.execute("SELECT review_id, source FROM material ORDER BY review_id").fetchall()
        assert [dict(row) for row in materials] == [
            {"review_id": "toeic.part5.20260804.0001", "source": "toeic"},
            {"review_id": "toeic.part5.20260804.0002", "source": "toeic"},
        ]

        generated = connection.execute(
            "SELECT COUNT(*) AS n FROM generated_item WHERE kind = 'grammar'"
        ).fetchone()["n"]
        assert generated == 2


def test_import_is_idempotent(tmp_path):
    items = [_grammar_item("時制")]
    with connect(tmp_path / "english.db") as connection:
        first = import_toeic_part5(connection, "20260804", items)
        second = import_toeic_part5(connection, "20260804", items)

    assert first == 1
    assert second == 0
