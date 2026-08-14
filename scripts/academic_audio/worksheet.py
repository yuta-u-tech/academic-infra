"""Build the printed worksheet (問題冊子 + 解答) as LuaLaTeX.

音声だけでは学習が完結しない。設問・正解・解説は紙で要る。科目リポジトリの TeX とは
別系統の独立した文書として組み、Drive へは単体の PDF として上げる。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .formats import ListeningFormat
from .items import ListeningSet, PassageSet, _label

# 科目リポジトリと同じ lualatex を使う。日本語と英語が同居するので luatexja。
_PREAMBLE = r"""\documentclass[a4paper,11pt]{ltjsarticle}
\usepackage{luatexja}
\usepackage[margin=25mm]{geometry}
\usepackage{amssymb}
\usepackage{enumitem}
\usepackage{hyperref}
\usepackage{graphicx}
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


def _youtube_line(youtube_url: str | None) -> list[str]:
    if not youtube_url:
        return []
    return [r"\par\noindent\textbf{音声（YouTube・限定公開）:} \url{" + youtube_url + "}", ""]


def _form_line(form_url: str | None) -> list[str]:
    if not form_url:
        return []
    # 1つのFormに冊子内の全設問をまとめて登録するので（1問1リンクではない）、
    # 冊子の先頭に1回だけ出す。hyperref は既にpreambleで読み込み済み。
    return [r"\par\noindent\textbf{回答フォーム（自動採点）:} \href{" + form_url + r"}{回答フォームはこちら}", ""]


def render_tex(
    listening_set: ListeningSet,
    listening_format: ListeningFormat,
    youtube_url: str | None = None,
    form_url: str | None = None,
) -> str:
    """Two sections: the questions to solve, then the answer key."""
    lines = [
        _PREAMBLE,
        r"\title{" + escape(listening_set.title) + "}",
        r"\date{}",
        r"\begin{document}",
        r"\maketitle",
        r"\section*{" + escape(listening_format.name) + "}",
        "",
        *_youtube_line(youtube_url),
        *_form_line(form_url),
        _instructions(listening_format),
        "",
    ]

    lines.append(r"\begin{enumerate}[label=\textbf{\arabic*.}]")
    for item in listening_set.items:
        lines.append(r"  \item")
        if listening_format.id == "toeic-part1" and item.image_path:
            # Part1(写真描写)は選択肢こそ音声のみだが、写真は見ながら解く形式なので
            # 冊子には写真だけを印刷する（Part2は本当に何も印刷しないが、Part1は
            # 「音声のみ」なのは描写文の方だけで、写真は視覚情報として必須）。
            lines.append(r"    \includegraphics[width=0.8\linewidth]{" + item.image_path + "}")
        elif listening_format.answer_in_audio:
            # 本番の Part 2 は冊子に何も印刷されない（質問文も選択肢も音声のみ）。
            # それに合わせ、設問ページは空欄にする。
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
        if item.pronunciation_note:
            lines.append(r"    \par\noindent\textit{発音: " + escape(item.pronunciation_note) + "}")
    lines.append(r"\end{enumerate}")
    lines.append(r"\end{document}")
    return "\n".join(lines) + "\n"


def _instructions(listening_format: ListeningFormat) -> str:
    if listening_format.id == "toeic-part1":
        return (
            "写真を見て、それを最もよく描写している文を音声で聴いた "
            r"(A)〜(D) から1つ選びなさい。文自体は音声のみで、冊子には印刷されません。"
        )
    if listening_format.id.startswith("toeic-part2"):
        return (
            "音声を聴き、質問または発言に対する応答として最も適切なものを "
            r"(A)〜(C) から1つ選びなさい。音声に正解は含まれません。"
        )
    return "音声を聴いて設問に答えなさい。"


def render_passage_tex(
    passage_set: PassageSet,
    listening_format: ListeningFormat,
    youtube_url: str | None = None,
    form_url: str | None = None,
) -> str:
    """grouping: passage 用（TOEIC Part 3/4）。

    設問ページには passage（会話・説明文）を出さない。聴いて答える形式なので、
    印刷してしまうと聴解にならない。passage は解答ページ（スクリプト確認用）にだけ出す。
    """
    lines = [
        _PREAMBLE,
        r"\title{" + escape(passage_set.title) + "}",
        r"\date{}",
        r"\begin{document}",
        r"\maketitle",
        r"\section*{" + escape(listening_format.name) + "}",
        "",
        *_youtube_line(youtube_url),
        *_form_line(form_url),
        _passage_instructions(listening_format),
        "",
    ]

    lines.append(r"\begin{enumerate}[label=\textbf{\arabic*.}]")
    for item in passage_set.items:
        for question in item.questions:
            lines.append(r"  \item " + escape(question.text))
            lines.append(r"    \begin{enumerate}[label=(\Alph*)]")
            for choice in question.choices:
                lines.append(r"      \item " + escape(choice))
            lines.append(r"    \end{enumerate}")
    lines.append(r"\end{enumerate}")

    lines.extend(["", r"\clearpage", r"\section*{スクリプトと解答}", ""])
    for item_number, item in enumerate(passage_set.items, start=1):
        lines.append(r"\subsection*{問題 " + str(item_number) + "}")
        lines.append(r"\begin{quote}\noindent")
        for line in item.passage:
            lines.append(escape(f"{line.speaker}: {line.text}") + r"\\")
        lines.append(r"\end{quote}")
        lines.append(r"\begin{enumerate}[label=\textbf{\arabic*.}]")
        for question in item.questions:
            lines.append(r"  \item \textbf{正解: " + escape(_label(question.answer_index) or "—") + "} " + escape(question.text))
            for choice_index, choice in enumerate(question.choices):
                marker = r"$\checkmark$ " if choice_index == question.answer_index else ""
                lines.append(
                    r"    \par\noindent\hspace{1em}(" + escape(_label(choice_index) or "") + ") "
                    + marker + escape(choice)
                )
            lines.append(r"    \par\medskip\noindent " + escape(question.explanation))
            if question.pronunciation_note:
                lines.append(r"    \par\noindent\textit{発音: " + escape(question.pronunciation_note) + "}")
        lines.append(r"\end{enumerate}")
    lines.append(r"\end{document}")
    return "\n".join(lines) + "\n"


def _passage_instructions(listening_format: ListeningFormat) -> str:
    if listening_format.id.startswith("toeic-part3"):
        return "音声で会話を聴き、続く3つの設問それぞれについて最も適切な答えを (A)〜(D) から選びなさい。"
    if listening_format.id.startswith("toeic-part4"):
        return "音声で説明文を聴き、続く3つの設問それぞれについて最も適切な答えを (A)〜(D) から選びなさい。"
    return "音声を聴いて、続く設問に答えなさい。"


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
