"""Build the printed worksheet (問題冊子 + 解答) as LuaLaTeX.

音声だけでは学習が完結しない。設問・正解・解説は紙で要る。科目リポジトリの TeX とは
別系統の独立した文書として組み、Drive へは単体の PDF として上げる。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .formats import ListeningFormat
from .items import ListeningSet, _label

# 科目リポジトリと同じ lualatex を使う。日本語と英語が同居するので luatexja。
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

_LATEX_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


class WorksheetError(Exception):
    pass


def escape(text: str) -> str:
    return "".join(_LATEX_ESCAPES.get(char, char) for char in text)


def render_tex(listening_set: ListeningSet, listening_format: ListeningFormat) -> str:
    """Two sections: the questions to solve, then the answer key."""
    lines = [
        _PREAMBLE,
        r"\title{" + escape(listening_set.title) + "}",
        r"\date{}",
        r"\begin{document}",
        r"\maketitle",
        r"\section*{" + escape(listening_format.name) + "}",
        "",
        _instructions(listening_format),
        "",
    ]

    lines.append(r"\begin{enumerate}[label=\textbf{\arabic*.}]")
    for item in listening_set.items:
        lines.append(r"  \item")
        if listening_format.answer_in_audio:
            # 選択肢を音声で読む形式では、冊子に選択肢を書かない（先に読まれてしまう）。
            lines.append(r"    \hfill")
        else:
            lines.append(r"    \begin{enumerate}[label=(\Alph*)]")
            for choice in item.parts_with_role("choice"):
                lines.append(r"      \item " + escape(choice.text))
            lines.append(r"    \end{enumerate}")
    lines.append(r"\end{enumerate}")

    lines.extend(["", r"\clearpage", r"\section*{解答と解説}", ""])
    lines.append(r"\begin{enumerate}[label=\textbf{\arabic*.}]")
    for item in listening_set.items:
        label = _label(item.answer_index)
        lines.append(r"  \item \textbf{正解: " + escape(label or "—") + "}")
        for part in item.parts_with_role("question"):
            lines.append(r"    \par\medskip\noindent 設問: " + escape(part.text))
        for index, choice in enumerate(item.parts_with_role("choice")):
            marker = r"$\checkmark$ " if index == item.answer_index else ""
            lines.append(
                r"    \par\noindent\hspace{1em}(" + escape(_label(index) or "") + ") "
                + marker + escape(choice.text)
            )
        lines.append(r"    \par\medskip\noindent " + escape(item.explanation))
    lines.append(r"\end{enumerate}")
    lines.append(r"\end{document}")
    return "\n".join(lines) + "\n"


def _instructions(listening_format: ListeningFormat) -> str:
    if listening_format.id.startswith("toeic-part2"):
        return (
            "音声を聴き、質問または発言に対する応答として最も適切なものを "
            r"(A)〜(C) から1つ選びなさい。音声に正解は含まれません。"
        )
    return "音声を聴いて設問に答えなさい。"


def build_pdf(tex_path: Path) -> Path:
    """Run latexmk the same way the course repositories do."""
    command = [
        "latexmk",
        "-lualatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-outdir={tex_path.parent}",
        f"-auxdir={tex_path.parent}",
        str(tex_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    pdf_path = tex_path.with_suffix(".pdf")
    if completed.returncode != 0 or not pdf_path.exists():
        raise WorksheetError(_latex_error(completed.stdout, completed.stderr, tex_path))
    return pdf_path


def _latex_error(stdout: str, stderr: str, tex_path: Path) -> str:
    errors = re.findall(r"^!.*$", stdout, re.MULTILINE)
    detail = "\n".join(errors[:5]) or stderr.strip() or stdout[-800:]
    return f"{tex_path} の組版に失敗しました。\n{detail}"
