"""チェックボックス付き単語帳（flashcard_render/flashcard_record）のテスト。"""

from __future__ import annotations

from pypdf import PdfReader, PdfWriter

from acenglish import study
from acenglish.db import connect
from acenglish.generate import ingest, upsert_material
from acenglish.items import GeneratedItem, GenerationResult, VocabItem
from acenglish.sources import ExternalMaterial
from acenglish.vocab_quiz import weak_review_ids
from toeic_reading.flashcard_record import read_checked_review_ids, reset_checkboxes
from toeic_reading.flashcard_render import FlashcardEntry, field_name, render_flashcard_tex


def _seed_word(connection, review_id: str, word: str, meaning: str) -> None:
    material = ExternalMaterial(
        review_id=review_id, title=word, body=word, source_file="study-forge",
        source_commit="deck-v1", source="toeic", origin="study-forge",
    )
    upsert_material(connection, material)
    result = GenerationResult(
        review_id=review_id, course_id="english", source_commit="deck-v1",
        generated_by="test", prompt_version="v1", is_ephemeral=False,
        items=[GeneratedItem(difficulty=3, reason="test",
                              item=VocabItem(word=word, meaning=meaning, example=f"{word}."))],
    )
    ingest(connection, result)


def _check_box(pdf_path, out_path, review_ids: list[str]) -> None:
    reader = PdfReader(pdf_path)
    writer = PdfWriter()
    writer.append(reader)
    updates = {field_name(rid): "/Yes" for rid in review_ids}
    for page in writer.pages:
        writer.update_page_form_field_values(page, updates, auto_regenerate=False)
    with open(out_path, "wb") as file:
        writer.write(file)


def test_flashcard_field_names_survive_hyperref_and_pypdf(tmp_path):
    """review_idをドット区切りのフィールド名にすれば、hyperrefのアンダースコア除去問題を
    避けつつ、pypdfのget_fields()で元のreview_idにそのまま戻せることを確認する。"""
    from academic_audio.worksheet import build_pdf

    entries = [
        FlashcardEntry(review_id="toeic.words1-400.0001", word="following", meaning="続いて"),
        FlashcardEntry(review_id="toeic.words1-400.0002", word="assure", meaning="保証する"),
    ]
    tex_path = tmp_path / "flashcards.tex"
    tex_path.write_text(render_flashcard_tex("test", entries), encoding="utf-8")
    pdf_path = build_pdf(tex_path)

    reader = PdfReader(pdf_path)
    fields = reader.get_fields()
    assert field_name("toeic.words1-400.0001") in fields
    assert field_name("toeic.words1-400.0002") in fields
    for field in fields.values():
        assert field["/V"] == "/Off"


def test_read_checked_review_ids_and_reset(tmp_path):
    from academic_audio.worksheet import build_pdf

    entries = [
        FlashcardEntry(review_id="toeic.words1-400.0001", word="following", meaning="続いて"),
        FlashcardEntry(review_id="toeic.words1-400.0002", word="assure", meaning="保証する"),
        FlashcardEntry(review_id="toeic.words1-400.0003", word="discreet", meaning="思慮深い"),
    ]
    tex_path = tmp_path / "flashcards.tex"
    tex_path.write_text(render_flashcard_tex("test", entries), encoding="utf-8")
    pdf_path = build_pdf(tex_path)

    checked_path = tmp_path / "checked.pdf"
    _check_box(pdf_path, checked_path, ["toeic.words1-400.0002"])

    checked = read_checked_review_ids(checked_path)
    assert checked == {"toeic.words1-400.0002"}

    reset_path = tmp_path / "reset.pdf"
    reset_checkboxes(checked_path, reset_path, [e.review_id for e in entries])
    assert read_checked_review_ids(reset_path) == set()


def test_record_flashcards_updates_weak_review_ids(tmp_path):
    connection = connect(tmp_path / "english.db")
    _seed_word(connection, "toeic.words1-400.0001", "following", "続いて")
    _seed_word(connection, "toeic.words1-400.0002", "assure", "保証する")

    # 0002だけ「分からなかった」として記録する。
    session_id = study.start_session(connection, "english")
    outcome_unknown = study.record_form_response(
        connection, session_id, "toeic.words1-400.0002", "分からなかった", correct_override=False,
    )
    outcome_known = study.record_form_response(
        connection, session_id, "toeic.words1-400.0001", "分かった", correct_override=True,
    )
    study.end_session(connection, session_id)

    assert outcome_unknown.correct is False
    assert outcome_known.correct is True
    assert weak_review_ids(connection) == ["toeic.words1-400.0002"]

    # 次のラウンドで0002を「分かった」に更新すると、weak一覧から外れる。
    session_id2 = study.start_session(connection, "english")
    study.record_form_response(
        connection, session_id2, "toeic.words1-400.0002", "分かった", correct_override=True,
    )
    study.end_session(connection, session_id2)
    assert weak_review_ids(connection) == []
    connection.close()
