"""The handover to the publisher (Issue #3).

#3 は「結合済み音声・台本・発話タイムライン・各種 hash・AudioArtifact メタデータ」を
前提にしている。動画のチャプターは問題単位（`item_id`）で切るため、タイムラインは
セグメント単位と item 単位の両方を持つ。
"""

from __future__ import annotations

import hashlib
import json
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .models import DialogueScript


@dataclass(frozen=True)
class SegmentTiming:
    segment_id: str
    item_id: str | None
    role: str | None
    speaker: str
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Chapter:
    """1問 = 1チャプター。#3 の YouTube チャプターにそのまま渡せる形。"""

    item_id: str
    start: float
    end: float
    title: str


@dataclass(frozen=True)
class AudioArtifact:
    job_id: str
    title: str
    source_id: str
    source_commit: str
    engine: str
    mode: str
    audio_path: str
    duration: float
    sample_rate: int
    channels: int
    script_hash: str
    audio_hash: str
    source_hash: str
    segments: list[SegmentTiming] = field(default_factory=list)
    chapters: list[Chapter] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_timeline(script: DialogueScript, segments_dir: Path, rendered: list[str]) -> list[SegmentTiming]:
    """Walk the rendered segments in script order, accumulating `pause` as the renderer does."""
    rendered_ids = set(rendered)
    timings: list[SegmentTiming] = []
    cursor = 0.0
    for segment in script.segments:
        if segment.id not in rendered_ids:
            continue
        duration = _wav_seconds(segments_dir / f"{segment.id}.wav")
        timings.append(
            SegmentTiming(
                segment_id=segment.id,
                item_id=segment.item_id,
                role=segment.role,
                speaker=segment.speaker,
                start=round(cursor, 3),
                end=round(cursor + duration, 3),
                text=segment.text,
            )
        )
        cursor += duration + max(segment.pause, 0.0)
    return timings


def build_chapters(timings: list[SegmentTiming]) -> list[Chapter]:
    chapters: list[Chapter] = []
    for timing in timings:
        if timing.item_id is None:
            continue
        if chapters and chapters[-1].item_id == timing.item_id:
            chapters[-1] = Chapter(
                item_id=timing.item_id,
                start=chapters[-1].start,
                end=timing.end,
                title=chapters[-1].title,
            )
            continue
        number = len(chapters) + 1
        chapters.append(Chapter(item_id=timing.item_id, start=timing.start, end=timing.end, title=f"第{number}問"))
    return chapters


def build_artifact(
    *,
    job,
    script: DialogueScript,
    script_path: Path,
    audio_path: Path,
    rendered: list[str],
) -> AudioArtifact:
    segments_dir = audio_path.parent / "segments"
    timings = build_timeline(script, segments_dir, rendered)
    channels, sample_rate, duration = _wav_params(audio_path)
    return AudioArtifact(
        job_id=job.job_id,
        title=script.title,
        source_id=script.source_id,
        source_commit=script.source_commit,
        engine=job.engine,
        mode=job.mode,
        audio_path=str(audio_path),
        duration=round(duration, 3),
        sample_rate=sample_rate,
        channels=channels,
        script_hash=file_hash(script_path),
        audio_hash=file_hash(audio_path),
        source_hash=text_hash(f"{script.source_id}@{script.source_commit}"),
        segments=timings,
        chapters=build_chapters(timings),
    )


def write_artifact(artifact: AudioArtifact, job_dir: Path) -> Path:
    path = job_dir / "artifact.json"
    path.write_text(json.dumps(artifact.to_json_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / handle.getframerate()


def _wav_params(path: Path) -> tuple[int, int, float]:
    with wave.open(str(path), "rb") as handle:
        return handle.getnchannels(), handle.getframerate(), handle.getnframes() / handle.getframerate()
