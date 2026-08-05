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
from acenglish.sources.toeic_part7 import Part7Passage  # noqa: E402

__all__ = ["build_pdf", "render_md", "render_reading_md", "render_reading_tex", "render_tex"]

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


def render_md(title: str, items: list[GrammarItem]) -> str:
    """ChatGPTにfree-formで解かせるためのMarkdown版。

    render_tex()と同じ「設問→解答解説→パターン凡例」の3段構成を、`---` 区切りで
    1ファイルに収める（PDFの「設問ページ→解答ページ」という2部構成と同じ考え方）。
    ChatGPT/ユーザーには「まず設問セクションだけ読んで進める」よう伝える前提で、
    答えを別ファイルへ分離するような新しい隠蔽の仕組みは作らない。
    """
    lines = [f"# {title}", "", "## Part 5 — 空所補充", "",
              "文の空所に入れるのに最も適切な語句を (A)〜(D) から1つ選びなさい。", ""]

    for index, item in enumerate(items, start=1):
        lines.append(f"{index}. {item.sentence}")
        for label, choice in zip(_LABELS, item.choices):
            lines.append(f"   - ({label}) {choice}")
        lines.append("")

    lines.extend(["---", "", "## 解答と解説", ""])
    for index, item in enumerate(items, start=1):
        label = _LABELS[item.answer_index] if item.answer_index < len(_LABELS) else "?"
        lines.append(f"{index}. **正解: {label}**（{item.point}・パターン{item.pattern}）")
        lines.append("")
        lines.append(f"   {item.explanation}")
        lines.append("")
        lines.append(f"   [パターン{item.pattern}の理由] {item.pattern_note}")
        lines.append("")

    lines.extend(["---", "", "## パターンについて", ""])
    for label, description in _PATTERN_LEGEND:
        lines.append(f"- **{label}**: {description}")
    lines.append("")

    return "\n".join(lines) + "\n"


def _reading_numbering(passages: list[Part7Passage]) -> list[tuple[int, Part7Passage, list[int]]]:
    """パッセージごとに、そこに属する設問の通し番号を割り当てる。

    実際のPart7と同じく設問は文書全体で通し番号にする（パッセージごとに1から
    振り直さない）一方、本文はパッセージにつき1回だけ表示する。
    """
    numbered = []
    running = 1
    for passage in passages:
        indices = list(range(running, running + len(passage.questions)))
        numbered.append((running, passage, indices))
        running += len(passage.questions)
    return numbered


def render_reading_tex(title: str, passages: list[Part7Passage]) -> str:
    numbered = _reading_numbering(passages)
    lines = [
        _PREAMBLE,
        r"\title{" + escape(title) + "}",
        r"\date{}",
        r"\begin{document}",
        r"\maketitle",
        r"\section*{Part 7 — 読解}",
        "",
        "文書を読み、各設問について最も適切な答えを (A)〜(D) から1つ選びなさい。",
        "",
    ]

    for _, passage, indices in numbered:
        lines.append(r"\par\noindent " + escape(passage.passage).replace("\n", r"\par "))
        # 設問番号はパッセージごとに1から振り直さず文書全体の通し番号にするので、
        # enumerate自身の\arabic*カウンタは使わず\itemに明示ラベルを渡す。
        lines.append(r"\begin{enumerate}[label={}]")
        for number, question in zip(indices, passage.questions):
            lines.append(r"  \item[\textbf{" + str(number) + r".}] " + escape(question.question))
            lines.append(r"    \begin{enumerate}[label=(\Alph*)]")
            for choice in question.choices:
                lines.append(r"      \item " + escape(choice))
            lines.append(r"    \end{enumerate}")
        lines.append(r"\end{enumerate}")
        lines.append(r"\clearpage")

    lines.extend([r"\section*{解答と解説}", ""])
    for _, passage, indices in numbered:
        for number, question in zip(indices, passage.questions):
            label = _LABELS[question.answer_index] if question.answer_index < len(_LABELS) else "?"
            lines.append(
                r"\par\noindent \textbf{" + str(number) + r". 正解: " + escape(label) + r"}"
            )
            lines.append(r"\par " + escape(question.explanation))
            lines.append("")

    lines.append(r"\end{document}")
    return "\n".join(lines) + "\n"


def render_reading_md(title: str, passages: list[Part7Passage]) -> str:
    """ChatGPTにfree-formで解かせるためのMarkdown版（render_md()のPart7版）。

    本文はパッセージにつき1回だけ表示し、配下の設問は通し番号でまとめる。
    答えはrender_md()と同じく `---` で区切った別セクションに置き、設問セクションには
    漏らさない。
    """
    numbered = _reading_numbering(passages)
    lines = [f"# {title}", "", "## Part 7 — 読解", "",
              "文書を読み、各設問について最も適切な答えを (A)〜(D) から1つ選びなさい。", ""]

    for passage_number, (_, passage, indices) in enumerate(numbered, start=1):
        lines.append(f"### パッセージ {passage_number}（{passage.passage_type}）")
        lines.append("")
        lines.append(passage.passage)
        lines.append("")
        for number, question in zip(indices, passage.questions):
            lines.append(f"{number}. {question.question}")
            for label, choice in zip(_LABELS, question.choices):
                lines.append(f"   - ({label}) {choice}")
            lines.append("")

    lines.extend(["---", "", "## 解答と解説", ""])
    for _, passage, indices in numbered:
        for number, question in zip(indices, passage.questions):
            label = _LABELS[question.answer_index] if question.answer_index < len(_LABELS) else "?"
            lines.append(f"{number}. **正解: {label}**")
            lines.append("")
            lines.append(f"   {question.explanation}")
            lines.append("")

    return "\n".join(lines) + "\n"
