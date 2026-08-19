"""個人TeX単語ノート(\\card{}形式)の取り込みのテスト。"""

from __future__ import annotations

from acenglish import fetch
from acenglish.db import connect
from acenglish.generate import ingest, upsert_material
from acenglish.items import GeneratedItem, GenerationResult, VocabItem
from acenglish.sources import ExternalMaterial
from acenglish.sources.personal_notes import parse_cards
from acenglish.vocab_quiz import load_pool

_SAMPLE_TEX = r"""
\card{Assure}{v.}{保証する}{I assure you it is safe.}
\card{Cacophony}{n.}{<<the \textasciitilde{}>> 都会の騒音}{The street was full of cacophony.}
\card{Assure}{v.}{保証する(重複)}{Duplicate within the same file.}
"""


def test_parse_cards_handles_nested_braces_and_reads_all_four_args():
    cards = parse_cards(_SAMPLE_TEX)
    assert len(cards) == 3
    assert cards[0] == ("Assure", "v.", "保証する", "I assure you it is safe.")
    # \textasciitilde{} の中の {} で壊れず、意味フィールド全体が読めていること。
    assert cards[1][0] == "Cacophony"
    assert "textasciitilde" in cards[1][2]


def test_import_personal_notes_tex_dedupes_within_file_and_against_pool(tmp_path):
    connection = connect(tmp_path / "english.db")

    # プールに既に "assure" がある状態を作る。
    material = ExternalMaterial(
        review_id="toeic.words1-400.0001", title="assure", body="assure",
        source_file="study-forge", source_commit="deck-v1", source="toeic",
        origin="study-forge",
    )
    upsert_material(connection, material)
    ingest(connection, GenerationResult(
        review_id="toeic.words1-400.0001", course_id="english", source_commit="deck-v1",
        generated_by="test", prompt_version="v1", is_ephemeral=False,
        items=[GeneratedItem(difficulty=3, reason="test",
                              item=VocabItem(word="assure", meaning="保証する"))],
    ))

    tex_path = tmp_path / "notes.tex"
    tex_path.write_text(_SAMPLE_TEX, encoding="utf-8")

    result = fetch.import_personal_notes_tex(connection, tex_path)
    # 3件中: assureはプールに既存(1件)+ファイル内重複(1件)でスキップ、Cacophonyだけ新規。
    assert result == {
        "total_cards_in_file": 3,
        "imported": 1,
        "skipped_duplicate_or_existing": 2,
    }

    pool_words = {e.word.casefold() for e in load_pool(connection)}
    assert "cacophony" in pool_words

    # 再実行しても増えない(冪等)。
    second = fetch.import_personal_notes_tex(connection, tex_path)
    assert second["imported"] == 0
    connection.close()
