import json

from acenglish import fetch, generate
from acenglish.db import connect
from acenglish.model import due_items
from acenglish.sources import ExternalMaterial
from tests.test_english_loop import _result


def test_duplicate_vocab_direction_is_idempotent(tmp_path):
    connection = connect(tmp_path / "english.db")
    target = ExternalMaterial(
        review_id="toeic.words1-400.0001", title="word", body="word",
        source_file="study-forge", source_commit="deck-v1", source="toeic",
        origin="study-forge",
    )
    generate.upsert_material(connection, target)
    result = _result().model_copy(update={
        "review_id": target.review_id, "course_id": "english", "source_commit": "deck-v1"})
    generate.ingest(connection, result)

    first = fetch.duplicate_vocab_direction(connection, "toeic", "recognition")
    second = fetch.duplicate_vocab_direction(connection, "toeic", "recognition")
    assert first == {"duplicated": 1, "skipped": 0, "recall": 1, "recognition": 1}
    assert second == {"duplicated": 0, "skipped": 1, "recall": 1, "recognition": 1}
    rows = connection.execute(
        "SELECT review_id, payload FROM generated_item WHERE kind='vocab' ORDER BY id"
    ).fetchall()
    assert len(rows) == 2
    assert rows[1]["review_id"] == "toeic.words1-400.0001.recog"
    assert json.loads(rows[1]["payload"])["sub_skill"] == "recognition"
    queued_sub_skills = [json.loads(row["payload"])["sub_skill"]
                         for row in due_items(connection, "english", limit=2, kinds=["vocab"])]
    assert queued_sub_skills == ["recall", "recognition"]
    connection.close()
