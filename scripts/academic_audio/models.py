"""Data contracts for Academic Audio jobs and dialogue scripts."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Literal

EngineName = Literal["auto", "piper", "style-bert-vits2", "wav"]
AudioMode = Literal["fast", "balanced", "quality"]
JobStatus = Literal["planned", "rendering", "completed", "failed"]


@dataclass(frozen=True)
class AudioSource:
    source_id: str
    title: str
    course_id: str | None
    review_id: str | None
    source_file: str | None
    section_file: str | None
    source_commit: str
    body: str


@dataclass(frozen=True)
class DialogueSegment:
    id: str
    speaker: str
    text: str
    language: str = "ja"
    emotion: str = "neutral"
    speed: float = 1.0
    pause: float = 0.35
    source_section: str | None = None


_SEGMENT_FIELDS = {field_.name for field_ in fields(DialogueSegment)}
_REQUIRED_SEGMENT_FIELDS = ("id", "speaker", "text")


def _segment_from_json_dict(raw: Any, index: int) -> DialogueSegment:
    if not isinstance(raw, dict):
        raise ValueError(f"segments[{index}] がオブジェクトではありません。")
    unknown = sorted(set(raw) - _SEGMENT_FIELDS)
    if unknown:
        raise ValueError(
            f"segments[{index}] に未知のフィールドがあります: {', '.join(unknown)}"
            f"（使えるのは {', '.join(sorted(_SEGMENT_FIELDS))}）"
        )
    missing = [key for key in _REQUIRED_SEGMENT_FIELDS if not raw.get(key)]
    if missing:
        raise ValueError(f"segments[{index}] に {', '.join(missing)} がありません。")
    try:
        return DialogueSegment(**raw)
    except TypeError as error:  # 型が違う場合（speed に文字列など）
        raise ValueError(f"segments[{index}]: {error}") from error


@dataclass(frozen=True)
class DialogueScript:
    title: str
    source_id: str
    source_commit: str
    segments: list[DialogueSegment]

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> "DialogueScript":
        """Build a script from JSON.

        `audio/prompts/*.md` に従って人手や Claude が書いた dialogue.json も通るため、
        壊れた入力は TypeError ではなく、どこが悪いか分かる ValueError で落とす。
        """
        for key in ("title", "source_id"):
            if not data.get(key):
                raise ValueError(f"dialogue.json に {key} がありません。")
        raw_segments = data.get("segments") or []
        if not raw_segments:
            raise ValueError("dialogue.json の segments が空です。")

        segments: list[DialogueSegment] = []
        seen_ids: set[str] = set()
        for index, raw in enumerate(raw_segments, start=1):
            segments.append(_segment_from_json_dict(raw, index))
            if segments[-1].id in seen_ids:
                raise ValueError(f"segments[{index}]: id '{segments[-1].id}' が重複しています。")
            seen_ids.add(segments[-1].id)

        return cls(
            title=data["title"],
            source_id=data["source_id"],
            source_commit=data.get("source_commit", "unknown"),
            segments=segments,
        )

    def write(self, output_dir: Path) -> tuple[Path, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / "dialogue.json"
        md_path = output_dir / "dialogue.md"
        json_path.write_text(
            json.dumps(self.to_json_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        lines = [f"# {self.title}", "", f"- source: `{self.source_id}`", ""]
        for segment in self.segments:
            lines.append(
                f"## {segment.id} / {segment.speaker} / {segment.language} / speed {segment.speed:g}"
            )
            lines.append("")
            lines.append(segment.text)
            lines.append("")
        md_path.write_text("\n".join(lines), encoding="utf-8")
        return json_path, md_path


@dataclass
class AudioJob:
    job_id: str
    status: JobStatus
    engine: str
    mode: str
    speed: float
    job_dir: str
    script_path: str
    output_path: str | None = None
    failed_segments: list[str] = field(default_factory=list)
    rendered_segments: list[str] = field(default_factory=list)
    error: str | None = None

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> "AudioJob":
        return cls(**data)
