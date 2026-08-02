"""Title / description / tags for a YouTube upload, derived from AudioArtifact.

Pure functions — no network, no filesystem — so they're easy to check before
ever calling the YouTube API.
"""

from __future__ import annotations

from dataclasses import dataclass

from .artifact import AudioArtifact

_TITLE_LIMIT = 100  # YouTube's hard limit
_DESCRIPTION_LIMIT = 5000  # YouTube's hard limit


@dataclass(frozen=True)
class VideoMetadata:
    title: str
    description: str
    tags: list[str]
    category_id: str = "27"  # Education


def describe(artifact: AudioArtifact) -> VideoMetadata:
    title = _truncate(artifact.title, _TITLE_LIMIT)
    description = _truncate(_build_description(artifact), _DESCRIPTION_LIMIT)
    tags = _build_tags(artifact)
    return VideoMetadata(title=title, description=description, tags=tags)


def _build_description(artifact: AudioArtifact) -> str:
    lines = [
        "Academic Audio が生成した学習音声です。",
        "",
        f"出典: {artifact.source_id}（commit {artifact.source_commit[:12]}）",
        f"生成: {artifact.engine} / {artifact.mode}",
    ]
    # YouTube はチャプターが認識されるために先頭が 0:00 で始まっている必要がある。
    if artifact.chapters and artifact.chapters[0].start == 0.0:
        lines += ["", "チャプター:"]
        lines += [f"{_timestamp(chapter.start)} {chapter.title}" for chapter in artifact.chapters]
    return "\n".join(lines)


def _build_tags(artifact: AudioArtifact) -> list[str]:
    tags = ["academic-audio"]
    subject = artifact.source_id.split(".")[0]
    if subject:
        tags.append(subject)
    return tags


def _timestamp(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."
