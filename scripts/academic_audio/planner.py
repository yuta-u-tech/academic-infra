"""Deterministic content and dialogue planning."""

from __future__ import annotations

import re
from itertools import islice

from .models import AudioSource, DialogueScript, DialogueSegment

_HEADING = re.compile(r"^#{1,3}\s+(.+)$", re.MULTILINE)
_BULLET = re.compile(r"^\s*[-*]\s+(.+)$", re.MULTILINE)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def summarize_points(source: AudioSource, limit: int = 6) -> list[str]:
    headings = [_clean(match.group(1)) for match in _HEADING.finditer(source.body)]
    bullets = [_clean(match.group(1)) for match in _BULLET.finditer(source.body)]
    paragraphs = [
        _clean(part)
        for part in re.split(r"\n\s*\n", source.body)
        if _clean(part) and not part.lstrip().startswith("#")
    ]
    points = [p for p in headings + bullets + paragraphs if p]
    return list(islice(dict.fromkeys(points), limit)) or [_clean(source.body)[:220]]


def create_dialogue(source: AudioSource, *, speed: float = 1.0) -> DialogueScript:
    points = summarize_points(source)
    segments: list[DialogueSegment] = [
        DialogueSegment(
            id="seg-001",
            speaker="host",
            text=f"今日は「{source.title}」を、音声で復習しやすい形に整理します。",
            speed=speed,
            source_section=source.review_id,
        )
    ]
    next_id = 2
    for index, point in enumerate(points, start=1):
        speaker = "learner" if index % 2 else "host"
        prefix = "確認したいです。" if speaker == "learner" else "要点はここです。"
        segments.append(
            DialogueSegment(
                id=f"seg-{next_id:03d}",
                speaker=speaker,
                text=f"{prefix} {point}",
                speed=speed,
                source_section=source.review_id,
            )
        )
        next_id += 1
    segments.append(
        DialogueSegment(
            id=f"seg-{next_id:03d}",
            speaker="host",
            text="最後に、重要語句を声に出して確認し、説明できるか試してみましょう。",
            speed=speed,
            source_section=source.review_id,
        )
    )
    return DialogueScript(
        title=source.title,
        source_id=source.source_id,
        source_commit=source.source_commit,
        segments=segments,
    )
