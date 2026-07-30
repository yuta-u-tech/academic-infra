"""外部素材の共通形。

`target.LearningTarget`（科目資料）と同じフィールドを持たせてあるので、`generate` から
先の経路は素材の出どころを気にしなくてよい。違うのは 2 つだけ:

- `source` — どこから来たか（`toeic` / `voa` / `ted`）
- `source_file` — 誤答が資料の不足と判定されたとき、**どのノートへ追記するか**の宛先。
  科目資料なら `src/chapters/ch02.tex`、外部素材なら `notes/vocabulary/toeic.md`。
  「直すべきファイル」という意味は同じなので、還元の処理を分岐させずに済む。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# 誤答が集中したときに追記する先。ドメインごとにノートを分ける。
_NOTE_DIRS = {
    "vocabulary": "notes/vocabulary",
    "grammar": "notes/grammar",
    "reading": "notes/reading",
    "listening": "notes/reading",
}
_DEFAULT_NOTE_DIR = "notes/vocabulary"


@dataclass(frozen=True)
class ExternalMaterial:
    """1つの学習対象。TOEIC なら1語、VOA/TED なら1記事・1トーク。"""

    review_id: str
    source: str
    title: str
    body: str
    origin: str
    source_file: str
    source_commit: str
    course_id: str = "english"
    chapter_title: str = ""
    section_file: str = ""

    def __post_init__(self) -> None:
        if not self.review_id.startswith(f"{self.source}."):
            raise ValueError(
                f"review_id は '{self.source}.' で始める必要があります: {self.review_id!r}"
            )


def slugify(value: str, max_length: int = 60) -> str:
    """URL やタイトルからファイル名・ID に使える断片を作る。

    日本語をローマ字化するようなことはしない（不安定で、見出しを直すたびに ID が
    変わる。既存 `sections.py` が連番を選んだのと同じ理由）。ASCII に落ちない文字は
    落とし、空になったら呼び出し側が別の識別子を渡す。
    """
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    return slug[:max_length] or "untitled"


def note_path_for(domain: str, topic: str) -> str:
    """誤答の還元先ノートのパス（english-notes リポジトリ内の相対パス）。"""
    directory = _NOTE_DIRS.get(domain, _DEFAULT_NOTE_DIR)
    return f"{directory}/{slugify(topic)}.md"
