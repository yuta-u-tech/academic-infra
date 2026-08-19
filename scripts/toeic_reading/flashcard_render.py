"""チェックボックス付き単語帳（PDF AcroForm）を LuaLaTeX で組む。

ボタンを押すデスクトップアプリの代わりに、紙/PDFの単語帳をそのまま自己採点用の
フォームにする。各語の1行に単語と意味を並べて表示し（隠さない）、右にチェックボックスを
1つだけ置く。**「分からなかった/要復習」をチェックする**（分かった語は無印のまま）。
これは `acenglish.vocab_quiz.weak_review_ids()`（直近の回答が不正解だった語）と対称な
設計で、そのままrecordして学習ループへcorrect_override（チェック=不正解 / 無印=正解）
として流し込める。

意味を答えページへ隠す構成（当初案）は、大量の語を高速に見て回って自己チェックする
用途（数千語規模）には合わないと判明（2026-08-19、実使用でのフィードバック）。
意味は各行にそのまま出す——このPDFは「思い出せるかを試す」ものではなく、
「知っているかを自己申告しながら高速に巡回する」ためのもの。

チェックボックスの `name=` に review_id をそのまま使うため、hyperref がフィールド名から
アンダースコア(`_`)を削る既知の問題（`_` は数式モードの下付き文字トリガーと解釈され、
サニタイズで消える）を避け、区切りは review_id が元々使っているドット(`.`)をそのまま使う
（動作確認済み: pypdf の `get_fields()` はドット入りの名前もフラットな1キーとして
そのまま返す。ネストしたAcroFormフィールド階層としては解釈されない）。

2000語超を印刷して見渡せる密度に収めるため、2段組（multicol）・小さめのフォントで組む
（個人のTeX単語ノート notes/vocabulary の \\card 形式と同じ発想）。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from academic_audio.worksheet import build_pdf, escape  # noqa: E402

__all__ = ["build_pdf", "render_flashcard_tex", "render_flashcard_md", "FlashcardEntry", "field_name"]

_PREAMBLE = r"""\documentclass[a4paper,10pt]{ltjsarticle}
\usepackage{luatexja}
\usepackage[margin=15mm]{geometry}
\usepackage{multicol}
\usepackage{enumitem}
\usepackage{hyperref}
\hypersetup{hidelinks}
\setlist[enumerate]{itemsep=2pt,topsep=2pt,leftmargin=1.4em}
\setlength{\columnsep}{10mm}
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
        "分からなかった/要復習の単語だけ、チェックボックスにチェックを入れてください"
        "（分かった単語はそのままでかまいません）。"
        "PDFを保存したら、そのファイルを"
        r"\texttt{toeic\_vocab\_cli.py record-flashcards} に渡して集計します。",
        "",
        r"\footnotesize",
        r"\begin{Form}",
        r"\begin{multicols}{2}",
        r"\raggedcolumns",
        r"\begin{enumerate}[label=\arabic*.]",
    ]
    for entry in entries:
        lines.append(
            r"  \item \CheckBox[name=" + field_name(entry.review_id)
            + r",width=8pt,height=8pt,bordercolor=0 0 0]{}\ "
            + r"\textbf{" + escape(entry.word) + "} = " + escape(entry.meaning)
        )
    lines.append(r"\end{enumerate}")
    lines.append(r"\end{multicols}")
    lines.append(r"\end{Form}")

    lines.append(r"\end{document}")
    return "\n".join(lines) + "\n"


def render_flashcard_md(title: str, entries: list[FlashcardEntry]) -> str:
    lines = [f"# {title}", ""]
    for index, entry in enumerate(entries, start=1):
        lines.append(f"{index}. {entry.word} = {entry.meaning}")
        if entry.example:
            lines.append(f"   {entry.example}")
    return "\n".join(lines) + "\n"
