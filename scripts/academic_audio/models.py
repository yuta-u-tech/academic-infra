"""Data contracts for Academic Audio jobs and dialogue scripts."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
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
        return cls(
            title=data["title"],
            source_id=data["source_id"],
            source_commit=data.get("source_commit", "unknown"),
            segments=[DialogueSegment(**segment) for segment in data.get("segments", [])],
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
