"""チェックボックス付き単語帳PDF（flashcard_render.py参照）の集計。

保存済みPDFのAcroFormフィールドを読み、「分からなかった」にチェックが入っている
review_idの集合を返す。あわせて、集計後に同じPDFのチェック状態を全て空へ戻した
コピーを書き出せる（同じファイルを次のラウンドでも使い回したい場合用）。
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter

from .flashcard_render import field_name

_PREFIX = "chk."


def read_checked_review_ids(pdf_path: Path) -> set[str]:
    reader = PdfReader(pdf_path)
    fields = reader.get_fields() or {}
    checked = set()
    for name, field in fields.items():
        if not name.startswith(_PREFIX):
            continue
        review_id = name[len(_PREFIX):]
        value = field.get("/V")
        if value not in (None, "/Off"):
            checked.add(review_id)
    return checked


def reset_checkboxes(pdf_path: Path, out_path: Path, review_ids: list[str]) -> Path:
    """全チェックを外したコピーを書き出す（同じPDFを次ラウンドでも使い回す用）。"""
    reader = PdfReader(pdf_path)
    writer = PdfWriter()
    writer.append(reader)
    updates = {field_name(review_id): "/Off" for review_id in review_ids}
    for page in writer.pages:
        writer.update_page_form_field_values(page, updates, auto_regenerate=False)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as file:
        writer.write(file)
    return out_path
