"""問題のPDF組版。

2026-08-06に出典（statisticsschool.com）由来の119問は解説の質に問題があり、Codexに
ゼロから生成し直させた。当初は出典の見た目（tcolorboxの色付きカード）を踏襲していたが、
Drive上の他の教材（TOEIC Part5/7・リスニング冊子。`academic_audio.worksheet`/
`toeic_reading.render`）とスタイルが揃っていなかったため、同じ house style
（`ltjsarticle`・geometry margin=25mm・色無し・「設問」→「解答と解説」の2部構成）に
統一した。`extract_raw_blocks()`/`extract_preamble()`は出典.texを再利用したくなった
場合のために残してあるが、現在は使っていない。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from academic_audio.worksheet import build_pdf  # noqa: E402
from academic_audio.worksheet import _PREAMBLE as _TOEIC_HOUSE_PREAMBLE  # noqa: E402

from .study import Problem  # noqa: E402

__all__ = [
    "HOUSE_PREAMBLE",
    "build_pdf",
    "build_worksheet_tex",
    "extract_preamble",
    "extract_raw_blocks",
    "render_generated_tex",
]

# TOEIC/リスニング冊子と同じhouse styleに、数式が多い統計用にamsmathだけ追加する
# （\operatorname 等がamssymbだけでは使えないため）。他の教材のプリアンブル自体は変えない。
HOUSE_PREAMBLE = _TOEIC_HOUSE_PREAMBLE + "\\usepackage{amsmath}\n"

_PTITLE_RE = re.compile(r"\\ptitle\{(\d+)\}\{[^}]*\}\{\d+\}")
_LABELS = ["A", "B", "C", "D", "E"]

# $...$（インライン）と \[...\]（ディスプレイ数式）の両方を保護区間として扱う。
_MATH_SPLIT_RE = re.compile(r"(\$[^$]*\$|\\\[.*?\\\])", re.DOTALL)

_LATEX_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


_DOUBLE_BACKSLASH_BRACKET_RE = re.compile(r"\\\\(?=[\[\]])")


def _fix_over_escaped_display_math(text: str) -> str:
    """CodexがJSON中で `\\[`/`\\]` を過剰エスケープして `\\\\[`/`\\\\]`（バックスラッシュ2つ）
    にしてしまうことがある（2026-08-06に実際に発生）。`\\[`を開始させるための単純な正規化。"""
    return _DOUBLE_BACKSLASH_BRACKET_RE.sub(r"\\", text)


def escape_outside_math(text: str) -> str:
    """`$...$`区間はそのままLaTeX数式として残し、それ以外の地の文だけをエスケープする。"""
    text = _fix_over_escaped_display_math(text)
    parts = _MATH_SPLIT_RE.split(text)
    escaped = []
    for index, part in enumerate(parts):
        if index % 2 == 1:  # 奇数インデックスは$...$で囲まれた数式区間
            escaped.append(part)
        else:
            escaped.append("".join(_LATEX_ESCAPES.get(char, char) for char in part))
    return "".join(escaped)


def render_generated_tex(title: str, problems: list[Problem]) -> str:
    """TOEIC Part5/7と同じ「設問→解答と解説」の2部構成で組む（`toeic_reading.render.render_tex`参照）。"""
    lines = [
        HOUSE_PREAMBLE,
        r"\title{" + escape_outside_math(title) + "}",
        r"\date{}",
        r"\begin{document}",
        r"\maketitle",
        r"\section*{設問}",
        "",
        "各設問について最も適切な答えを選びなさい。",
        "",
    ]

    lines.append(r"\begin{enumerate}[label=\textbf{\arabic*.}]")
    for problem in problems:
        lines.append(r"  \item " + escape_outside_math(problem.question))
        lines.append(r"    \begin{enumerate}[label=(\Alph*)]")
        for choice in problem.choices:
            lines.append(r"      \item " + escape_outside_math(choice))
        lines.append(r"    \end{enumerate}")
    lines.append(r"\end{enumerate}")

    lines.extend(["", r"\clearpage", r"\section*{解答と解説}", ""])
    lines.append(r"\begin{enumerate}[label=\textbf{\arabic*.}]")
    for problem in problems:
        label = _LABELS[problem.answer_index] if problem.answer_index < len(_LABELS) else "?"
        lines.append(r"  \item \textbf{正解: " + label + r"}")
        lines.append(r"    \par\medskip\noindent " + escape_outside_math(problem.explanation))
    lines.append(r"\end{enumerate}")

    lines.append(r"\end{document}")
    return "\n".join(lines) + "\n"


def extract_preamble(tex_path: Path) -> str:
    content = tex_path.read_text(encoding="utf-8")
    marker = content.index(r"\begin{document}")
    return content[:marker]


def extract_raw_blocks(tex_path: Path) -> dict[int, str]:
    """`\\ptitle{N}{...}{...}`から次の`\\ptitle`（または`\\end{document}`）直前までを、
    出現順のグローバル連番（1始まり）をキーにして返す。

    `\\ptitle{N}`のNはセクション内で1〜20に振り直されており文書全体ではユニークで
    ないため（例:「問題20」が12セクション分ある）、キーには使えない。
    `toukei_import_toketarou.py`のsource_numberも同じ採番規則（出現順）を使うこと。
    """
    content = tex_path.read_text(encoding="utf-8")
    headers = list(_PTITLE_RE.finditer(content))
    end_marker = content.index(r"\end{document}")

    blocks: dict[int, str] = {}
    for index, header in enumerate(headers):
        start = header.start()
        end = headers[index + 1].start() if index + 1 < len(headers) else end_marker
        block = content[start:end]
        # 次の問題の直前にある\clearpageは前の問題の一部として付いてくるので落とす。
        block = re.sub(r"\\clearpage\s*$", "", block.rstrip())
        blocks[index + 1] = block
    return blocks


def build_worksheet_tex(preamble: str, title: str, blocks: list[str]) -> str:
    """出典.texの生ブロックを束ねる旧経路（現在未使用、互換のため残置）。"""
    parts = [
        preamble,
        r"\begin{document}",
        r"\begin{center}\Large\bfseries " + title + r"\end{center}",
        r"\vspace{6pt}",
        "",
    ]
    parts.extend(block for block in blocks)
    parts.append(r"\end{document}")
    return "\n\n".join(parts) + "\n"
