"""Loading and validating `academic.yml`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class CourseConfig:
    """The per-repository settings an AI agent would otherwise have to guess."""

    course_id: str
    course_name: str
    main_tex: Path
    source_dir: Path
    chapters_dir: Path
    engine: str
    output_dir: Path
    drive_folder_name: str
    exclude_from_publish: tuple[str, ...]

    @property
    def build_dir(self) -> Path:
        return self.output_dir / "build"


_REQUIRED_KEYS = ("course_id", "course_name", "main_tex", "source_dir", "chapters_dir")
_SUPPORTED_ENGINES = ("lualatex",)


def load_course_config(path: Path) -> CourseConfig:
    """Read `academic.yml` from `path`, resolving paths against its directory."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise FileNotFoundError(
            f"{path} が見つかりません。科目リポジトリの直下に academic.yml を置いてください。"
        ) from error
    except yaml.YAMLError as error:
        raise ValueError(f"{path} をYAMLとして解釈できません: {error}") from error

    if not isinstance(raw, dict):
        raise ValueError(f"{path} のトップレベルはマッピングである必要があります。")

    missing = [key for key in _REQUIRED_KEYS if not raw.get(key)]
    if missing:
        raise ValueError(f"{path} に必須キーがありません: {', '.join(missing)}")

    engine = raw.get("engine", "lualatex")
    if engine not in _SUPPORTED_ENGINES:
        raise ValueError(
            f"{path}: engine={engine!r} は未対応です。対応: {', '.join(_SUPPORTED_ENGINES)}"
        )

    root = path.parent
    return CourseConfig(
        course_id=str(raw["course_id"]),
        course_name=str(raw["course_name"]),
        main_tex=root / str(raw["main_tex"]),
        source_dir=root / str(raw["source_dir"]),
        chapters_dir=root / str(raw["chapters_dir"]),
        engine=engine,
        output_dir=root / str(raw.get("output_dir", "dist")),
        drive_folder_name=str(raw.get("drive_folder_name", raw["course_name"])),
        exclude_from_publish=tuple(raw.get("exclude_from_publish", ()) or ()),
    )
