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


_PIPER_DEFAULT_TEMPLATE = "piper --output_file {out}"


class PiperEngine(CommandEngine):
    """Piper adapter.

    piper 1.x は音声モデル (`-m`) が必須で、読み上げテキストは標準入力から受け取る。
    `--piper-model` が渡された場合は既定の起動方法でそのまま生成でき、別の起動方法に
    したい場合だけ `--piper-command` のテンプレートを使う。
    """

    def __init__(self, command_template: str | None = None, model: str | None = None):
        super().__init__("piper", command_template or _PIPER_DEFAULT_TEMPLATE)
        self.model = model

    def available(self) -> tuple[bool, str]:
        ok, reason = super().available()
        if not ok:
            return ok, reason
        if self.command_template == _PIPER_DEFAULT_TEMPLATE:
            if not self.model:
                return False, "piper found, but no voice model. Pass --piper-model <voice.onnx>"
            if not Path(self.model).exists():
                return False, f"piper voice model not found: {self.model}"
            return True, f"piper found with model {self.model}"
        return ok, reason

    def model_language(self) -> str | None:
        """Return the voice model's language family (e.g. "en"), if the config is readable."""
        if not self.model:
            return None
        config = Path(f"{self.model}.json")
        if not config.exists():
            return None
        try:
            data = json.loads(config.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return (data.get("language") or {}).get("family")

    def render(self, segment: DialogueSegment, output_path: Path) -> None:
        if self.command_template != _PIPER_DEFAULT_TEMPLATE:
            super().render(segment, output_path)
            return
        if not self.model:
            raise TTSEngineError("piper voice model is not configured. Pass --piper-model <voice.onnx>")
        # 言語が違う音声モデルでも piper は成功してしまうが、出力は読み上げになっていない。
        # 黙って品質を落とさないよう、ここで落とす。
        model_language = self.model_language()
        if model_language and model_language != segment.language:
            raise TTSEngineError(
                f"piper voice model language is '{model_language}' but segment {segment.id} is "
                f"'{segment.language}'. Use a matching voice model, or another engine for this language."
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            "piper",
            "--model",
            self.model,
            "--output_file",
            str(output_path),
            # piper は話速を length_scale (長さ倍率) で受け取るため、speed の逆数を渡す。
            "--length_scale",
            f"{1.0 / segment.speed:.4f}" if segment.speed > 0 else "1.0",
        ]
        completed = subprocess.run(command, input=segment.text, capture_output=True, text=True)
        if completed.returncode != 0:
            raise TTSEngineError(completed.stderr.strip() or "piper failed")
        if not output_path.exists():
            raise TTSEngineError(f"piper did not create {output_path}")


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


class MultiSpeakerPiperEngine(TTSEngine):
    """Dispatch to a different Piper voice model per DialogueSegment.speaker.

    TOEIC Part 3 の会話は複数話者を音で聴き分けられないと成立しない。Piper は
    1回の起動につき1モデルしか使えないので、話者ラベルごとに別の PiperEngine を
    内部に持ち、segment.speaker で振り分ける。
    """

    name = "piper"

    def __init__(self, voice_map: dict[str, str]):
        if not voice_map:
            raise TTSEngineError('--piper-voice-map が必要です（例: "A=<voice1.onnx>,B=<voice2.onnx>,narrator=<voice1.onnx>"）')
        self.voice_map = voice_map
        self._engines = {speaker: PiperEngine(model=model) for speaker, model in voice_map.items()}

    def available(self) -> tuple[bool, str]:
        for speaker, engine in self._engines.items():
            ok, reason = engine.available()
            if not ok:
                return False, f"speaker '{speaker}': {reason}"
        return True, f"{len(self._engines)} 話者ぶんのモデルが揃っています: {', '.join(self.voice_map)}"

    def render(self, segment: DialogueSegment, output_path: Path) -> None:
        engine = self._engines.get(segment.speaker)
        if engine is None:
            raise TTSEngineError(
                f"speaker '{segment.speaker}' のモデルが --piper-voice-map にありません"
                f"（登録済み: {', '.join(self.voice_map)}）"
            )
        engine.render(segment, output_path)


def parse_speaker_map(raw: str) -> dict[str, str]:
    """Parse "A=path1,B=path2" into {"A": "path1", "B": "path2"}."""
    mapping: dict[str, str] = {}
    for pair in raw.split(","):
        speaker, _, value = pair.partition("=")
        if not speaker.strip() or not value.strip():
            raise TTSEngineError(f"--piper-voice-map の書式が不正です: {pair!r}")
        mapping[speaker.strip()] = value.strip()
    return mapping


def select_engine(
    engine: EngineName,
    mode: AudioMode,
    *,
    piper_command: str | None = None,
    piper_model: str | None = None,
    style_bert_command: str | None = None,
    style_bert_endpoint: str | None = None,
) -> TTSEngine:
    if engine == "wav":
        return WavEngine()
    if engine == "piper" or mode == "fast":
        return PiperEngine(piper_command, piper_model)
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
    return PiperEngine(piper_command, piper_model)
