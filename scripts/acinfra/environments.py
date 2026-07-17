"""Rewrite this project's tcolorbox environments into pandoc-readable LaTeX.

`protocol.tex` defines theorem-like boxes with `\\newtcbtheorem`, so the source
says::

    \\begin{definition}{線形リスト}{linear-list}
    線形リストとは ...
    \\end{definition}

Pandoc has no idea what `definition` is: it drops the two arguments and emits
the body as a bare paragraph, which loses the kind ("定義"), the title and the
label. Every such block is rewritten into a `quote` carrying a bold heading,
which pandoc turns into a blockquote whose first line names the block.
"""

from __future__ import annotations

from typing import NamedTuple

from .latex import read_arguments, read_optional


class BoxKind(NamedTuple):
    """How one environment should be rendered."""

    japanese_name: str
    label_prefix: str


# Mirrors the \newtcbtheorem calls in src/includes/protocol.tex. The prefixes
# match the auto-generated \ref keys (e.g. def:linear-list) so anchors in the
# Markdown line up with the labels used in the TeX.
THEOREM_BOXES: dict[str, BoxKind] = {
    "definition": BoxKind("定義", "def"),
    "theorem": BoxKind("定理", "th"),
    "proposition": BoxKind("命題", "prop"),
    "example": BoxKind("例", "ex"),
    "remark": BoxKind("注意", "rm"),
    "exercise": BoxKind("演習", "qs"),
    "exproblem": BoxKind("例題", "exprob"),
    "character": BoxKind("性質", "cha"),
    "solution": BoxKind("解答", "sol"),
    "tproof": BoxKind("証明", "prf"),
}

# Boxes taking [colour]{title} instead of {title}{label}.
TITLE_ONLY_BOXES = ("sidebox", "sbox")


def _heading(kind: str, title: str) -> str:
    title = title.strip()
    label = f"{kind}: {title}" if title else kind
    return rf"\textbf{{{label}}}"


def _rewrite_theorem_box(source: str, name: str, kind: BoxKind) -> str:
    """Rewrite every `\\begin{name}{title}{label}` block in `source`."""
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
        arguments, after_args = read_arguments(source, found + len(opener), 2)
        title = arguments[0] if arguments else ""
        # A missing label is tolerated: the box still renders, it just gets no
        # anchor. Bailing out here would silently drop the whole block.
        heading = _heading(kind.japanese_name, title)
        output.append(f"\\begin{{quote}}\n{heading}\n\n")
        cursor = after_args

        end = source.find(closer, cursor)
        if end == -1:  # unterminated block: emit the remainder untouched
            output.append(source[cursor:])
            return "".join(output)
        output.append(source[cursor:end])
        output.append("\n\\end{quote}\n")
        cursor = end + len(closer)


def _rewrite_title_box(source: str, name: str) -> str:
    """Rewrite every `\\begin{name}[colour]{title}` block in `source`."""
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
        _colour, after_optional = read_optional(source, found + len(opener))
        arguments, after_args = read_arguments(source, after_optional, 1)
        title = arguments[0] if arguments else ""
        output.append(f"\\begin{{quote}}\n{_heading('補足', title)}\n\n")
        cursor = after_args

        end = source.find(closer, cursor)
        if end == -1:
            output.append(source[cursor:])
            return "".join(output)
        output.append(source[cursor:end])
        output.append("\n\\end{quote}\n")
        cursor = end + len(closer)


def rewrite_boxes(source: str) -> str:
    """Rewrite all known tcolorbox environments into quote blocks."""
    result = source
    for name, kind in THEOREM_BOXES.items():
        result = _rewrite_theorem_box(result, name, kind)
    for name in TITLE_ONLY_BOXES:
        result = _rewrite_title_box(result, name)
    return result
