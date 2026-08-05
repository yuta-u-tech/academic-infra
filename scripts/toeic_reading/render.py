"""TOEIC Part 5（空所補充）の問題冊子を LuaLaTeX で組む。

`academic_audio.worksheet` と同じ「設問ページ→解答ページ」の2部構成・同じ
LaTeXエスケープ・同じ `latexmk -lualatex` ビルドを流用する。リスニングと
中身は別物でも、印刷物としての骨格は共有した方が保守が楽なため。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from academic_audio.worksheet import build_pdf, escape  # noqa: E402
from acenglish.items import GrammarItem  # noqa: E402

__all__ = ["build_pdf", "render_tex"]

_PREAMBLE = r"""\documentclass[a4paper,11pt]{ltjsarticle}
\usepackage{luatexja}
\usepackage[margin=25mm]{geometry}
\usepackage{amssymb}
\usepackage{enumitem}
\usepackage{hyperref}
\hypersetup{hidelinks}
\setlist[enumerate]{itemsep=2pt,topsep=4pt}
\renewcommand{\thesection}{}
"""

_LABELS = ["A", "B", "C", "D", "E"]

# english/prompts/grammar.md の分類定義と一致させる。
_PATTERN_LEGEND = [
    ("パターンA", "同じ語の別の形（品詞・時制・態など）。形を正しく選べるかを問う。"),
    ("パターンB", "似ているが別の語（スペルや音が近い、意味の異なる語）。語彙の意味を問う。"),
    ("パターンC", "コロケーション知識。文法だけでは絞れず、その語と実際に結びつく語の組み合わせを問う。"),
]


def render_tex(title: str, items: list[GrammarItem]) -> str:
    lines = [
        _PREAMBLE,
        r"\title{" + escape(title) + "}",
        r"\date{}",
        r"\begin{document}",
        r"\maketitle",
        r"\section*{Part 5 — 空所補充}",
        "",
        "文の空所に入れるのに最も適切な語句を (A)〜(D) から1つ選びなさい。",
        "",
    ]

    lines.append(r"\begin{enumerate}[label=\textbf{\arabic*.}]")
    for item in items:
        before, _, after = item.sentence.partition("____")
        sentence = escape(before) + r"\underline{\hspace{2.5em}}" + escape(after)
        lines.append(r"  \item " + sentence)
        lines.append(r"    \begin{enumerate}[label=(\Alph*)]")
        for choice in item.choices:
            lines.append(r"      \item " + escape(choice))
        lines.append(r"    \end{enumerate}")
    lines.append(r"\end{enumerate}")

    lines.extend(["", r"\clearpage", r"\section*{解答と解説}", ""])
    lines.append(r"\begin{enumerate}[label=\textbf{\arabic*.}]")
    for item in items:
        label = _LABELS[item.answer_index] if item.answer_index < len(_LABELS) else "?"
        lines.append(
            r"  \item \textbf{正解: " + escape(label) + r"（" + escape(item.point)
            + r"・パターン" + escape(item.pattern) + r"）}"
        )
        lines.append(r"    \par\medskip\noindent " + escape(item.explanation))
        lines.append(r"    \par\smallskip\noindent " + escape(f"[パターン{item.pattern}の理由] {item.pattern_note}"))
    lines.append(r"\end{enumerate}")

    lines.extend(["", r"\clearpage", r"\section*{パターンについて}", ""])
    lines.append(r"\begin{description}")
    for label, description in _PATTERN_LEGEND:
        lines.append(r"  \item[" + escape(label) + r"] " + escape(description))
    lines.append(r"\end{description}")

    lines.append(r"\end{document}")
    return "\n".join(lines) + "\n"
