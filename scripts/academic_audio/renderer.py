"""Render dialogue scripts into cached segment audio and a local WAV artifact."""

from __future__ import annotations

import hashlib
import json
import shutil
import wave
from pathlib import Path

from .engines import TTSEngine, TTSEngineError
from .models import DialogueScript, DialogueSegment
from .pronunciation import normalize


def cache_key(segment: DialogueSegment, engine_name: str) -> str:
    data = {
        "text": segment.text,
        "language": segment.language,
        "speaker": segment.speaker,
        "speed": segment.speed,
        "engine": engine_name,
        "emotion": segment.emotion,
    }
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def render_script(
    script: DialogueScript,
    engine: TTSEngine,
    *,
    job_dir: Path,
    cache_dir: Path,
    force: bool = False,
) -> tuple[list[str], list[str], Path]:
    segments_dir = job_dir / "segments"
    segments_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[str] = []
    failed: list[str] = []

    for segment in script.segments:
        normalized = DialogueSegment(
            **{**segment.__dict__, "text": normalize(segment.text)}
        )
        cached = cache_dir / f"{cache_key(normalized, engine.name)}.wav"
        output = segments_dir / f"{segment.id}.wav"
        if cached.exists() and not force:
            shutil.copyfile(cached, output)
            rendered.append(segment.id)
            continue
        try:
            engine.render(normalized, cached)
            shutil.copyfile(cached, output)
            rendered.append(segment.id)
        except TTSEngineError:
            failed.append(segment.id)
    final = job_dir / "output.wav"
    if rendered:
        concatenate_wav([segments_dir / f"{segment_id}.wav" for segment_id in rendered], final)
    return rendered, failed, final


def concatenate_wav(inputs: list[Path], output_path: Path) -> None:
    first = inputs[0]
    with wave.open(str(first), "rb") as source:
        params = source.getparams()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as destination:
        destination.setparams(params)
        for path in inputs:
            with wave.open(str(path), "rb") as source:
                if source.getparams()[:3] != params[:3]:
                    raise TTSEngineError(f"WAV format mismatch: {path}")
                destination.writeframes(source.readframes(source.getnframes()))
