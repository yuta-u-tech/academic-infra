"""Building the publishable artefacts for one course repository."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import CourseConfig
from .latex import read_group

_SUBFILE = re.compile(r"\\subfile\s*")


@dataclass(frozen=True)
class BuildResult:
    """Where the LaTeX run left its output."""

    pdf: Path
    aux: Path
    log: Path
    total_pages: int


def chapters_in_main(main_tex: Path) -> list[str]:
    """Return the chapter stems `main.tex` actually includes, in order.

    A chapter file that exists but is not `\\subfile`d is absent from the PDF,
    so it can carry no page number.
    """
    source = main_tex.read_text(encoding="utf-8")
    stems: list[str] = []
    for match in _SUBFILE.finditer(source):
        group = read_group(source, match.end(), "{")
        if group is None:
            continue
        stems.append(Path(group.body.strip()).stem)
    return stems


_OUTPUT_WRITTEN = re.compile(r"Output written on .*?\((?P<pages>\d+) pages?,")


def _count_pages(log: Path) -> int:
    """Read the page count out of the LaTeX log.

    Counting from the PDF itself would need a PDF library: LuaTeX writes
    PDF 1.5+ object streams, so `/Count` is compressed and not greppable.
    The engine already reports the number it wrote, so trust that.
    """
    if not log.exists():
        return 0
    text = log.read_text(encoding="utf-8", errors="replace")
    matches = _OUTPUT_WRITTEN.findall(text)
    return int(matches[-1]) if matches else 0


def build_pdf(config: CourseConfig) -> BuildResult:
    """Compile `main.tex` with LuaLaTeX into the build directory.

    Raises RuntimeError on a compile error, with the tail of the LaTeX log
    attached: a silently missing PDF is worse than a loud failure.
    """
    config.build_dir.mkdir(parents=True, exist_ok=True)
    # -auxdir is pinned alongside -outdir on purpose. A personal ~/.latexmkrc
    # setting $aux_dir (as this developer's does) otherwise keeps .aux and .log
    # somewhere else, so the page mapping would work in CI and silently fail
    # locally -- or the reverse.
    command = [
        "latexmk",
        "-lualatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-file-line-error",
        "-synctex=1",
        f"-outdir={config.build_dir.resolve()}",
        f"-auxdir={config.build_dir.resolve()}",
        config.main_tex.name,
    ]
    completed = subprocess.run(
        command,
        cwd=config.main_tex.parent,
        capture_output=True,
        text=True,
    )

    stem = config.main_tex.stem
    pdf = config.build_dir / f"{stem}.pdf"
    log = config.build_dir / f"{stem}.log"
    aux = config.build_dir / f"{stem}.aux"

    if completed.returncode != 0 or not pdf.exists():
        detail = log.read_text(encoding="utf-8", errors="replace")[-3000:] if log.exists() else completed.stdout[-3000:]
        raise RuntimeError(f"LuaLaTeX のビルドに失敗しました。\n--- log tail ---\n{detail}")

    if not aux.exists():
        raise RuntimeError(
            f"PDF はできましたが {aux} がありません。ページ対応付けができないため中断します。"
            " latexmk の aux_dir 設定を確認してください。"
        )

    return BuildResult(pdf=pdf, aux=aux, log=log, total_pages=_count_pages(log))


def stage_pdf(result: BuildResult, config: CourseConfig) -> Path:
    """Copy the built PDF to `dist/latest.pdf`."""
    config.output_dir.mkdir(parents=True, exist_ok=True)
    destination = config.output_dir / "latest.pdf"
    shutil.copy2(result.pdf, destination)
    return destination
