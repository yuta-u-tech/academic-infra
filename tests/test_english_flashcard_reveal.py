"""flashcard_reveal.py（タップで開閉する単語帳）のテスト。

実際にLuaLaTeXを2語分だけ走らせるため他のテストより時間がかかる
（目安3〜5秒）。3語以上に増やすと比例して遅くなるので、構造検証に
必要な最小限の語数に留めている。
"""

from __future__ import annotations

import pikepdf

from toeic_reading.flashcard_render import FlashcardEntry, field_name
from toeic_reading.flashcard_reveal import build_dual_checkbox_flashcards, reveal_field_name


def test_build_dual_checkbox_flashcards_has_custom_appearances_for_both_boxes(tmp_path):
    entries = [
        FlashcardEntry(review_id="toeic.words1-400.0001", word="following", meaning="続いて"),
        FlashcardEntry(review_id="toeic.words1-400.0002", word="assure", meaning="保証する"),
    ]
    out_pdf = build_dual_checkbox_flashcards("test", entries, tmp_path / "build")
    assert out_pdf.exists()

    pdf = pikepdf.open(out_pdf)
    assert pdf.Root.AcroForm.NeedAppearances is False

    page = pdf.pages[0]
    fields_seen = set()
    for annot in page.Annots:
        if annot.get("/Subtype") != pikepdf.Name.Widget:
            continue
        name = str(annot.get("/T", ""))
        fields_seen.add(name)
        ap = annot.get("/AP")
        assert ap is not None, f"{name} has no custom /AP"
        n = ap.get("/N")
        assert "/Off" in n and "/Yes" in n, f"{name} missing Off/Yes appearance states"
        assert annot.get("/AS") == pikepdf.Name.Off

    for entry in entries:
        assert reveal_field_name(entry.review_id) in fields_seen
        assert field_name(entry.review_id) in fields_seen
    # 開閉用と自己申告用は別物のフィールド名であること。
    assert reveal_field_name(entries[0].review_id) != field_name(entries[0].review_id)
