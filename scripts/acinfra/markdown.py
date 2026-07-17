"""Converting chapter TeX into Markdown aimed at AI retrieval.

The goal is not a faithful rendering of the PDF; it is text an AI can search,
quote and cite. Figures are therefore reduced to placeholders rather than
dropped silently, so a reader can tell that something visual was there.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .environments import rewrite_boxes
from .latex import read_group, strip_subfile_preamble

_PANDOC_FORMAT = "gfm+tex_math_dollars"

# Environments whose content is drawing instructions, not prose.
_FIGURE_ENVIRONMENTS = ("tikzpicture", "animateinline")


def _replace_environment(source: str, name: str, replacement: str) -> str:
    """Replace whole `\\begin{name}...\\end{name}` blocks with `replacement`."""
    opener = rf"\begin{{{name}}}"
    closer = rf"\end{{{name}}}"
    output: list[str] = []
    cursor = 0
    while True:
        found = source.find(opener, cursor)
        if found == -1:
            output.append(source[cursor:])
            return "".join(output)
        output.append(source[cursor:found])
        end = source.find(closer, found)
        if end == -1:
            output.append(source[found:])
            return "".join(output)
        output.append(replacement)
        cursor = end + len(closer)


def _replace_includegraphics(source: str) -> str:
    """Turn `\\includegraphics[...]{file}` into a readable placeholder."""
    output: list[str] = []
    cursor = 0
    macro = r"\includegraphics"
    while True:
        found = source.find(macro, cursor)
        if found == -1:
            output.append(source[cursor:])
            return "".join(output)
        output.append(source[cursor:found])
        after = found + len(macro)
        optional = read_group(source, after, "[")
        if optional is not None:
            after = optional.end
        mandatory = read_group(source, after, "{")
        if mandatory is None:
            output.append(macro)
            cursor = after
            continue
        output.append(f"\n\n（図: {Path(mandatory.body.strip()).name}）\n\n")
        cursor = mandatory.end


def preprocess(source: str) -> str:
    """Prepare one chapter's TeX for pandoc."""
    body = strip_subfile_preamble(source)
    body = rewrite_boxes(body)
    for environment in _FIGURE_ENVIRONMENTS:
        body = _replace_environment(body, environment, "\n\n（図は元PDFを参照）\n\n")
    body = _replace_includegraphics(body)
    return body


def _tidy(markdown: str) -> str:
    """Collapse the blank-line noise the rewrites leave behind."""
    without_runs = re.sub(r"\n{3,}", "\n\n", markdown)
    return without_runs.strip() + "\n"


def convert_to_markdown(source: str) -> str:
    """Convert one chapter's TeX to Markdown via pandoc.

    Raises RuntimeError when pandoc is missing or rejects the input, because a
    silently empty chapter would poison the knowledge base without any signal.
    """
    prepared = preprocess(source)
    try:
        completed = subprocess.run(
            ["pandoc", "--from=latex", f"--to={_PANDOC_FORMAT}", "--wrap=none"],
            input=prepared,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as error:
        raise RuntimeError(
            "pandoc が見つかりません。Markdown 生成には pandoc が必要です。"
        ) from error
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"pandoc がTeXの変換に失敗しました: {error.stderr.strip()}") from error

    return _tidy(completed.stdout)
