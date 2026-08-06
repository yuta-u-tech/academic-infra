"""毎回、出典.texから該当問題を切り出し直してPDFを組み直す。

`toukei_import_toketarou.py` が取り込むテキスト（quiz用にLaTeXコマンドを平文化した
ものをDBへ保存）とは別に、こちらは出典 `.tex` の生のLaTeXブロック（`\\ptitle`〜
`\\end{explainbox}`）をそのまま切り出して束ね直す。数式・tcolorboxのレイアウトは
出典の元々の定義（プリアンブル）に頼るので、平文化による崩れが起きない。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from academic_audio.worksheet import build_pdf  # noqa: E402

__all__ = ["build_pdf", "build_worksheet_tex", "extract_preamble", "extract_raw_blocks"]

_PTITLE_RE = re.compile(r"\\ptitle\{(\d+)\}\{[^}]*\}\{\d+\}")


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
