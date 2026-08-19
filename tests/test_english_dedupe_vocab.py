"""fetch.dedupe_vocab() のテスト。"""

from __future__ import annotations

from acenglish import fetch
from acenglish.db import connect
from acenglish.generate import ingest, upsert_material
from acenglish.items import GeneratedItem, GenerationResult, VocabItem
from acenglish.sources import ExternalMaterial
from acenglish.vocab_quiz import load_pool_by_direction


def _seed(connection, review_id: str, word: str, meaning: str, example: str = "") -> None:
    material = ExternalMaterial(
        review_id=review_id, title=word, body=word, source_file="study-forge",
        source_commit="deck-v1", source="toeic", origin="study-forge",
    )
    upsert_material(connection, material)
    ingest(connection, GenerationResult(
        review_id=review_id, course_id="english", source_commit="deck-v1",
        generated_by="test", prompt_version="v1", is_ephemeral=False,
        items=[GeneratedItem(difficulty=3, reason="test",
                              item=VocabItem(word=word, meaning=meaning, example=example or None))],
    ))


def test_dedupe_vocab_keeps_entry_with_example_and_retires_the_rest(tmp_path):
    connection = connect(tmp_path / "english.db")
    _seed(connection, "toeic.words1-400.0001", "cashier", "レジ係")
    _seed(connection, "toeic.supplement2.0094", "cashier", "レジ係", example="The cashier scanned the items.")
    _seed(connection, "toeic.words1-400.0002", "assure", "保証する")  # 重複なし

    fetch.duplicate_vocab_direction(connection, "toeic", "recognition")

    result = fetch.dedupe_vocab(connection)
    assert result == {"duplicate_word_groups": 1, "retired_rows": 2}

    pool = load_pool_by_direction(connection, "recognition")
    words = [e.word for e in pool]
    assert words.count("cashier") == 1
    assert words.count("assure") == 1

    kept = next(e for e in pool if e.word == "cashier")
    assert kept.review_id == "toeic.supplement2.0094.recog"
    assert kept.example == "The cashier scanned the items."

    retired = connection.execute(
        "SELECT retired_at FROM generated_item WHERE review_id = 'toeic.words1-400.0001'"
    ).fetchone()
    assert retired["retired_at"] is not None
    retired_recog = connection.execute(
        "SELECT retired_at FROM generated_item WHERE review_id = 'toeic.words1-400.0001.recog'"
    ).fetchone()
    assert retired_recog["retired_at"] is not None

    # 再実行しても増えない(冪等)。
    second = fetch.dedupe_vocab(connection)
    assert second == {"duplicate_word_groups": 0, "retired_rows": 0}
    connection.close()
