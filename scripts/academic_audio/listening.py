"""Generate listening, shadowing, and dictation scripts from line-based materials."""

from __future__ import annotations

import re

from .models import AudioSource, DialogueScript, DialogueSegment


def split_sentences(text: str, limit: int = 20) -> list[str]:
    pieces = re.split(r"(?<=[。.!?])\s+|\n+", text)
    cleaned = [re.sub(r"\s+", " ", piece).strip(" -") for piece in pieces]
    return [piece for piece in cleaned if len(piece) >= 3][:limit]


def create_listening_script(
    source: AudioSource,
    *,
    mode: str,
    speed: float,
    limit: int = 20,
) -> DialogueScript:
    segments: list[DialogueSegment] = []
    for index, sentence in enumerate(split_sentences(source.body, limit), start=1):
        segments.append(
            DialogueSegment(
                id=f"seg-{index:03d}",
                speaker="narrator",
                text=_mode_text(sentence, mode),
                language="en" if sentence.isascii() else "ja",
                speed=speed,
                pause=0.5,
                source_section=source.review_id,
            )
        )
    return DialogueScript(
        title=f"{source.title} listening {mode} {speed:g}x",
        source_id=source.source_id,
        source_commit=source.source_commit,
        segments=segments,
    )


def _mode_text(sentence: str, mode: str) -> str:
    if mode == "shadowing":
        return f"{sentence} {sentence}"
    if mode == "dictation":
        return f"{sentence} Write what you heard."
    return sentence
