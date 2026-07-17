"""Minimal LaTeX source scanning helpers.

Regexes cannot match balanced braces, and this project's TeX uses titles that
contain macros (e.g. ``\\begin{remark}{なぜ \\texttt{prev} が要るのか}{prev}``).
Everything here therefore works by scanning for balanced delimiters.
"""

from __future__ import annotations

from typing import NamedTuple


class Group(NamedTuple):
    """A brace/bracket group found in a source string."""

    body: str
    start: int
    end: int  # index just past the closing delimiter


_PAIRS = {"{": "}", "[": "]"}


def read_group(source: str, index: int, opener: str = "{") -> Group | None:
    """Read one balanced group starting at the first `opener` at/after `index`.

    Only whitespace may sit between `index` and the opener; anything else means
    the group is absent (e.g. an optional argument that was not supplied).
    Returns None when no group starts here.
    """
    if opener not in _PAIRS:
        raise ValueError(f"Unsupported opener: {opener!r}")
    closer = _PAIRS[opener]

    cursor = index
    while cursor < len(source) and source[cursor] in " \t\n\r":
        cursor += 1
    if cursor >= len(source) or source[cursor] != opener:
        return None

    depth = 0
    scan = cursor
    while scan < len(source):
        char = source[scan]
        if char == "\\":  # skip escaped characters such as \{ and \}
            scan += 2
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return Group(body=source[cursor + 1 : scan], start=cursor, end=scan + 1)
        scan += 1
    return None


def read_arguments(source: str, index: int, count: int) -> tuple[list[str], int]:
    """Read `count` mandatory `{...}` arguments starting at `index`.

    Returns the argument bodies and the index just past the last one. Stops
    early (returning fewer arguments) when a group is missing.
    """
    bodies: list[str] = []
    cursor = index
    for _ in range(count):
        group = read_group(source, cursor, "{")
        if group is None:
            break
        bodies.append(group.body)
        cursor = group.end
    return bodies, cursor


def read_optional(source: str, index: int) -> tuple[str | None, int]:
    """Read a single optional `[...]` argument starting at `index`."""
    group = read_group(source, index, "[")
    if group is None:
        return None, index
    return group.body, group.end


def strip_subfile_preamble(source: str) -> str:
    """Return the body of a `subfiles` document.

    Chapter files are standalone-compilable subfiles, so they carry a
    `\\documentclass[../main.tex]{subfiles}` preamble that must not reach the
    Markdown conversion. Files without `\\begin{document}` are returned as-is.
    """
    begin = source.find(r"\begin{document}")
    if begin == -1:
        return source
    body_start = begin + len(r"\begin{document}")
    end = source.rfind(r"\end{document}")
    body = source[body_start:end] if end != -1 else source[body_start:]
    return body.strip("\n")
