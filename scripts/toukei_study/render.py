"""問題のPDF組版。

2026-08-06に出典（statisticsschool.com）由来の119問は解説の質に問題があり、Codexに
ゼロから生成し直させた（`toukei_import_toketarou.py`は出典.texからの再取り込み用に
残すが既定では使わない）。Codex生成分は`source_number`を持たないため、構造化フィールド
（question/choices/answer_index/explanation）から直接LaTeXブロックを組む
`build_generated_block()`が既定の経路になる。`extract_raw_blocks()`は出典.texを
再利用したくなった場合のために残してある。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from academic_audio.worksheet import build_pdf  # noqa: E402

__all__ = [
    "GENERATED_PREAMBLE",
    "build_generated_block",
    "build_pdf",
    "build_worksheet_tex",
    "extract_preamble",
    "extract_raw_blocks",
]

_PTITLE_RE = re.compile(r"\\ptitle\{(\d+)\}\{[^}]*\}\{\d+\}")

_LABELS = ["A", "B", "C", "D", "E"]

# 出典.tex（problems_statistics_applied.tex）のtcolorbox定義を踏襲した自己完結プリアンブル。
# 数式はCodex生成分がそのまま有効なLaTeXとして出力する前提なのでエスケープしない。
GENERATED_PREAMBLE = r"""\documentclass[a4paper,10pt]{ltjsarticle}
\usepackage[margin=17mm]{geometry}
\usepackage{luatexja}
\usepackage{amsmath,amssymb,mathtools}
\usepackage{enumitem,multicol}
\usepackage[most]{tcolorbox}
\usepackage{xcolor}

\definecolor{mainblue}{HTML}{1F4E79}
\definecolor{softblue}{HTML}{EEF5FB}
\definecolor{softgreen}{HTML}{F0F7F2}
\definecolor{linegray}{HTML}{D7DEE8}

\setlength{\parindent}{0pt}
\setlength{\parskip}{0.4em}
\setlist{itemsep=0.15em,topsep=0.2em}

\newtcolorbox{problemcard}{%
  breakable,enhanced,colback=white,colframe=mainblue,
  boxrule=0.7pt,arc=1.5mm,left=2mm,right=2mm,top=1mm,bottom=1mm}
\newtcolorbox{answerbox}{%
  breakable,enhanced,colback=softgreen,colframe=green!40!black,
  boxrule=0.5pt,arc=1.5mm,left=2mm,right=2mm,top=0.8mm,bottom=0.8mm}
\newtcolorbox{explainbox}{%
  breakable,enhanced,colback=softblue,colframe=linegray,
  boxrule=0.5pt,arc=1.5mm,left=2mm,right=2mm,top=1mm,bottom=1mm}
"""


def build_generated_block(number: int, question: str, choices: list[str], answer_index: int, explanation: str) -> str:
    """Codex生成分の構造化フィールドから、出典と同じ見た目のLaTeXブロックを組む。"""
    label = _LABELS[answer_index] if answer_index < len(_LABELS) else "?"
    lines = [
        r"\subsection*{問題~" + str(number) + "}",
        r"\begin{problemcard}",
        r"\textbf{問題文}\par",
        question,
        "",
        r"\medskip\textbf{選択肢}\par",
        r"\begin{multicols}{2}",
        r"\begin{enumerate}[label=\Alph*.]",
    ]
    lines.extend(r"\item " + choice for choice in choices)
    lines.extend([
        r"\end{enumerate}",
        r"\end{multicols}",
        r"\end{problemcard}",
        r"\begin{answerbox}",
        r"\textbf{正答}\quad " + label + ". " + choices[answer_index],
        r"\end{answerbox}",
        r"\begin{explainbox}",
        r"\textbf{解説}\par",
        explanation,
        r"\end{explainbox}",
    ])
    return "\n".join(lines)


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
