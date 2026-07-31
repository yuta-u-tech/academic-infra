"""TTS engine adapters for Piper, Style-Bert-VITS2, and deterministic tests."""

from __future__ import annotations

import json
import math
import shlex
import shutil
import subprocess
import urllib.error
import urllib.request
import wave
from pathlib import Path

from .models import AudioMode, DialogueSegment, EngineName


class TTSEngineError(Exception):
    pass


class TTSEngine:
    name = "base"

    def available(self) -> tuple[bool, str]:
        return False, "not implemented"

    def render(self, segment: DialogueSegment, output_path: Path) -> None:
        raise NotImplementedError


class WavEngine(TTSEngine):
    """Generate short valid WAV files without external dependencies."""

    name = "wav"

    def available(self) -> tuple[bool, str]:
        return True, "built-in test renderer"

    def render(self, segment: DialogueSegment, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sample_rate = 22050
        duration = max(0.25, min(2.0, len(segment.text) / 80.0))
        frames = int(sample_rate * duration)
        frequency = 440 if segment.speaker == "host" else 554
        with wave.open(str(output_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            for index in range(frames):
                value = int(8000 * math.sin(2 * math.pi * frequency * index / sample_rate))
                wav.writeframesraw(value.to_bytes(2, "little", signed=True))


class CommandEngine(TTSEngine):
    def __init__(self, name: str, command_template: str):
        self.name = name
        self.command_template = command_template

    def available(self) -> tuple[bool, str]:
        executable = shlex.split(self.command_template)[0]
        if shutil.which(executable):
            return True, f"{executable} found"
        return False, f"{executable} is not installed"

    def render(self, segment: DialogueSegment, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            part.format(
                text=segment.text,
                out=str(output_path),
                speaker=segment.speaker,
                speed=segment.speed,
                language=segment.language,
                emotion=segment.emotion,
            )
            for part in shlex.split(self.command_template)
        ]
        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.returncode != 0:
            raise TTSEngineError(completed.stderr.strip() or completed.stdout.strip() or command)
        if not output_path.exists():
            raise TTSEngineError(f"TTS command did not create {output_path}")


class PiperEngine(CommandEngine):
    def __init__(self, command_template: str | None = None):
        super().__init__(
            "piper",
            command_template or "piper --output_file {out}",
        )

    def render(self, segment: DialogueSegment, output_path: Path) -> None:
        if self.command_template == "piper --output_file {out}":
            output_path.parent.mkdir(parents=True, exist_ok=True)
            completed = subprocess.run(
                ["piper", "--output_file", str(output_path)],
                input=segment.text,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                raise TTSEngineError(completed.stderr.strip() or "piper failed")
            if not output_path.exists():
                raise TTSEngineError(f"piper did not create {output_path}")
            return
        super().render(segment, output_path)


class StyleBertVITS2Engine(TTSEngine):
    name = "style-bert-vits2"

    def __init__(self, command_template: str | None = None, endpoint: str | None = None):
        self.command_template = command_template
        self.endpoint = endpoint

    def available(self) -> tuple[bool, str]:
        if self.command_template:
            executable = shlex.split(self.command_template)[0]
            return (True, f"{executable} configured") if shutil.which(executable) else (False, f"{executable} is not installed")
        if self.endpoint:
            return True, f"endpoint configured: {self.endpoint}"
        return False, "configure --style-bert-command or --style-bert-endpoint"

    def render(self, segment: DialogueSegment, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if self.command_template:
            return CommandEngine(self.name, self.command_template).render(segment, output_path)
        if not self.endpoint:
            raise TTSEngineError("Style-Bert-VITS2 renderer is not configured")
        payload = json.dumps(
            {
                "text": segment.text,
                "speaker": segment.speaker,
                "language": segment.language,
                "speed": segment.speed,
                "emotion": segment.emotion,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                output_path.write_bytes(response.read())
        except urllib.error.URLError as error:
            raise TTSEngineError(str(error)) from error


def select_engine(
    engine: EngineName,
    mode: AudioMode,
    *,
    piper_command: str | None = None,
    style_bert_command: str | None = None,
    style_bert_endpoint: str | None = None,
) -> TTSEngine:
    if engine == "wav":
        return WavEngine()
    if engine == "piper" or mode == "fast":
        return PiperEngine(piper_command)
    if engine == "style-bert-vits2" or mode == "quality":
        selected = StyleBertVITS2Engine(style_bert_command, style_bert_endpoint)
        ok, reason = selected.available()
        if not ok and mode == "quality":
            raise TTSEngineError(reason)
        return selected

    style = StyleBertVITS2Engine(style_bert_command, style_bert_endpoint)
    ok, _ = style.available()
    if ok and mode == "balanced":
        return style
    return PiperEngine(piper_command)
