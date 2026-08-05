"""TOEIC 単語テスト（語彙MCQ）の問題冊子を LuaLaTeX で組む。

Part5/Part7 と同じ「設問ページ→解答ページ」の骨格を流用する。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from academic_audio.worksheet import build_pdf, escape  # noqa: E402

__all__ = ["build_pdf", "render_tex", "render_md", "QuizQuestion"]

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


@dataclass(frozen=True)
class QuizQuestion:
    review_id: str
    word: str
    choices: list[str]
    answer_index: int
    meaning: str
    example: str


def render_tex(title: str, questions: list[QuizQuestion]) -> str:
    lines = [
        _PREAMBLE,
        r"\title{" + escape(title) + "}",
        r"\date{}",
        r"\begin{document}",
        r"\maketitle",
        r"\section*{語彙テスト}",
        "",
        "次の単語の意味として最も適切なものを (A)〜(D) から1つ選びなさい。",
        "",
    ]
    lines.append(r"\begin{enumerate}[label=\textbf{\arabic*.}]")
    for question in questions:
        lines.append(r"  \item " + escape(question.word))
        lines.append(r"    \begin{enumerate}[label=(\Alph*)]")
        for choice in question.choices:
            lines.append(r"      \item " + escape(choice))
        lines.append(r"    \end{enumerate}")
    lines.append(r"\end{enumerate}")

    lines.extend(["", r"\clearpage", r"\section*{解答}", ""])
    lines.append(r"\begin{enumerate}[label=\textbf{\arabic*.}]")
    for question in questions:
        label = _LABELS[question.answer_index] if question.answer_index < len(_LABELS) else "?"
        lines.append(
            r"  \item \textbf{正解: " + escape(label) + r"}\quad "
            + escape(question.word) + " = " + escape(question.meaning)
        )
        if question.example:
            lines.append(r"    \par\smallskip\noindent " + escape(question.example))
    lines.append(r"\end{enumerate}")

    lines.append(r"\end{document}")
    return "\n".join(lines) + "\n"


def render_md(title: str, questions: list[QuizQuestion]) -> str:
    lines = [
        f"# {title}", "", "## 語彙テスト", "",
        "次の単語の意味として最も適切なものを (A)〜(D) から1つ選びなさい。", "",
    ]
    for index, question in enumerate(questions, start=1):
        lines.append(f"{index}. {question.word}")
        for label, choice in zip(_LABELS, question.choices):
            lines.append(f"   - ({label}) {choice}")
        lines.append("")

    lines.extend(["## 解答", ""])
    for index, question in enumerate(questions, start=1):
        label = _LABELS[question.answer_index] if question.answer_index < len(_LABELS) else "?"
        lines.append(f"{index}. **正解: {label}**　{question.word} = {question.meaning}")
        if question.example:
            lines.append(f"   {question.example}")
        lines.append("")
    return "\n".join(lines) + "\n"
