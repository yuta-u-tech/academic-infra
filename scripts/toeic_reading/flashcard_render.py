"""チェックボックス付き単語帳（PDF AcroForm）を LuaLaTeX で組む。

ボタンを押すデスクトップアプリの代わりに、紙/PDFの単語帳をそのまま自己採点用の
フォームにする。各語の横に1つだけチェックボックスを置き、**「分からなかった」を
チェックする**（分かった語は無印のまま）。これは `acenglish.vocab_quiz.weak_review_ids()`
（直近の回答が不正解だった語）と対称な設計で、そのままrecordして学習ループへ
correct_override（チェック=不正解 / 無印=正解）として流し込める。

チェックボックスの `name=` に review_id をそのまま使うため、hyperref がフィールド名から
アンダースコア(`_`)を削る既知の問題（`_` は数式モードの下付き文字トリガーと解釈され、
サニタイズで消える）を避け、区切りは review_id が元々使っているドット(`.`)をそのまま使う
（動作確認済み: pypdf の `get_fields()` はドット入りの名前もフラットな1キーとして
そのまま返す。ネストしたAcroFormフィールド階層としては解釈されない）。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from academic_audio.worksheet import build_pdf, escape  # noqa: E402

__all__ = ["build_pdf", "render_flashcard_tex", "render_flashcard_md", "FlashcardEntry", "field_name"]

_PREAMBLE = r"""\documentclass[a4paper,11pt]{ltjsarticle}
\usepackage{luatexja}
\usepackage[margin=25mm]{geometry}
\usepackage{enumitem}
\usepackage{hyperref}
\hypersetup{hidelinks}
\setlist[enumerate]{itemsep=4pt,topsep=4pt}
"""


@dataclass(frozen=True)
class FlashcardEntry:
    review_id: str
    word: str
    meaning: str
    example: str = ""


def field_name(review_id: str) -> str:
    """AcroFormのフィールド名。review_idをそのまま使う（衝突しない一意な鍵のため）。"""
    return f"chk.{review_id}"


def render_flashcard_tex(title: str, entries: list[FlashcardEntry]) -> str:
    lines = [
        _PREAMBLE,
        r"\title{" + escape(title) + "}",
        r"\date{}",
        r"\begin{document}",
        r"\maketitle",
        r"\section*{単語帳}",
        "",
        "意味を思い出せなかった単語だけ、右のチェックボックスにチェックを入れてください"
        "（分かった単語はそのままでかまいません）。"
        "PDFを保存したら、そのファイルを"
        r"\texttt{toeic\_vocab\_cli.py record-flashcards} に渡して集計します。",
        "",
        r"\begin{Form}",
        r"\begin{enumerate}[label=\arabic*.]",
    ]
    for entry in entries:
        lines.append(
            r"  \item \textbf{" + escape(entry.word) + r"} \hfill "
            + r"\CheckBox[name=" + field_name(entry.review_id)
            + r",width=10pt,height=10pt,bordercolor=0 0 0]{}\ 分からなかった"
        )
    lines.append(r"\end{enumerate}")
    lines.append(r"\end{Form}")

    lines.extend(["", r"\clearpage", r"\section*{解答}", ""])
    lines.append(r"\begin{enumerate}[label=\arabic*.]")
    for entry in entries:
        lines.append(
            r"  \item \textbf{" + escape(entry.word) + "} = " + escape(entry.meaning)
        )
        if entry.example:
            lines.append(r"    \par\smallskip\noindent " + escape(entry.example))
    lines.append(r"\end{enumerate}")

    lines.append(r"\end{document}")
    return "\n".join(lines) + "\n"


def render_flashcard_md(title: str, entries: list[FlashcardEntry]) -> str:
    lines = [f"# {title}", "", "## 単語帳", ""]
    for index, entry in enumerate(entries, start=1):
        lines.append(f"{index}. {entry.word} = {entry.meaning}")
        if entry.example:
            lines.append(f"   {entry.example}")
    return "\n".join(lines) + "\n"
