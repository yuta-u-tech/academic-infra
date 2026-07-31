#!/usr/bin/env python3
"""Render text to WAV with Style-Bert-VITS2.

Academic Audio へは2通りで渡せる。

1回ずつ起動する（確認向け。1発話ごとに BERT を読み直すので遅い）:

  --style-bert-command "python3 scripts/style_bert_vits2_tts.py render \
    --output {out} --text {text} --speaker {speaker} --emotion {emotion} --speed {speed}"

常駐させる（バッチ向け。モデルを1回だけ読む）:

  python3 scripts/style_bert_vits2_tts.py serve --port 8787
  --style-bert-endpoint http://127.0.0.1:8787/render

モデルは事前に取得しておく。

  python3 -m pip install style-bert-vits2 "numpy<2" "setuptools<81"
  python3 scripts/style_bert_vits2_tts.py download
"""

from __future__ import annotations

import argparse
import json
import sys
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO
from pathlib import Path

DEFAULT_MODELS_DIR = Path(".venv/sbv2-models")
BERT_MODEL = "ku-nlp/deberta-v2-large-japanese-char-wwm"
# JVNV コーパス由来の話者 (CC BY-SA 4.0)。対話台本の speaker をこれに割り当てる。
DEFAULT_VOICE_MAP = {
    "host": "jvnv-F1-jp",
    "learner": "jvnv-M1-jp",
    "narrator": "jvnv-F1-jp",
}
MODEL_FILES = {
    "jvnv-F1-jp": "jvnv-F1-jp_e160_s14000.safetensors",
    "jvnv-M1-jp": "jvnv-M1-jp_e158_s14000.safetensors",
}
MODEL_REPO = "litagin/style_bert_vits2_jvnv"


class StyleBertVITS2Error(Exception):
    pass


def parse_voice_map(raw: str | None) -> dict[str, str]:
    if not raw:
        return dict(DEFAULT_VOICE_MAP)
    mapping = dict(DEFAULT_VOICE_MAP)
    for pair in raw.split(","):
        speaker, _, voice = pair.partition("=")
        if not speaker.strip() or not voice.strip():
            raise StyleBertVITS2Error(f"--voice-map の書式が不正です: {pair}")
        mapping[speaker.strip()] = voice.strip()
    return mapping


class Renderer:
    """Load the Japanese BERT once, then reuse it for every voice model."""

    def __init__(self, models_dir: Path, voice_map: dict[str, str], device: str = "cpu"):
        self.models_dir = models_dir
        self.voice_map = voice_map
        self.device = device
        self._models: dict[str, object] = {}
        self._load_bert()

    def _load_bert(self) -> None:
        from style_bert_vits2.constants import Languages
        from style_bert_vits2.nlp import bert_models

        # transformers v5 はチェックポイントの dtype (fp16) のまま読むが、
        # Style-Bert-VITS2 本体は float32 なので明示的に揃える。
        bert_models.load_model(Languages.JP, BERT_MODEL).float()
        bert_models.load_tokenizer(Languages.JP, BERT_MODEL)

    def _model(self, voice: str):
        if voice in self._models:
            return self._models[voice]
        from style_bert_vits2.tts_model import TTSModel

        directory = self.models_dir / voice
        checkpoint = MODEL_FILES.get(voice)
        if checkpoint is None:
            candidates = sorted(directory.glob("*.safetensors"))
            if not candidates:
                raise StyleBertVITS2Error(f"{directory} に .safetensors がありません。download を実行してください。")
            checkpoint = candidates[0].name
        if not (directory / checkpoint).exists():
            raise StyleBertVITS2Error(f"{directory / checkpoint} がありません。download を実行してください。")
        model = TTSModel(
            model_path=directory / checkpoint,
            config_path=directory / "config.json",
            style_vec_path=directory / "style_vectors.npy",
            device=self.device,
        )
        self._models[voice] = model
        return model

    def render(self, *, text: str, speaker: str, emotion: str, speed: float) -> bytes:
        voice = self.voice_map.get(speaker, DEFAULT_VOICE_MAP["host"])
        model = self._model(voice)
        style = _resolve_style(model, emotion)
        # Style-Bert-VITS2 は長さ倍率で受け取るため、speed の逆数を渡す。
        length = 1.0 / speed if speed > 0 else 1.0
        sample_rate, audio = model.infer(text=text, style=style, length=length)
        return _to_wav_bytes(audio, sample_rate)


def _resolve_style(model, emotion: str) -> str:
    styles = {name.lower(): name for name in model.style2id}
    return styles.get((emotion or "").lower(), "Neutral")


def _to_wav_bytes(audio, sample_rate: int) -> bytes:
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(audio.tobytes())
    return buffer.getvalue()


def _cmd_download(args: argparse.Namespace) -> int:
    from huggingface_hub import hf_hub_download

    for voice, checkpoint in MODEL_FILES.items():
        for name in (checkpoint, "config.json", "style_vectors.npy"):
            print(hf_hub_download(MODEL_REPO, f"{voice}/{name}", local_dir=str(args.models_dir)))
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    renderer = Renderer(args.models_dir, parse_voice_map(args.voice_map), device=args.device)
    payload = renderer.render(text=args.text, speaker=args.speaker, emotion=args.emotion, speed=args.speed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    renderer = Renderer(args.models_dir, parse_voice_map(args.voice_map), device=args.device)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler の規約
            length = int(self.headers.get("Content-Length", 0))
            try:
                request = json.loads(self.rfile.read(length) or b"{}")
                audio = renderer.render(
                    text=request["text"],
                    speaker=request.get("speaker", "host"),
                    emotion=request.get("emotion", "neutral"),
                    speed=float(request.get("speed", 1.0)),
                )
            except (KeyError, ValueError, StyleBertVITS2Error) as error:
                body = json.dumps({"error": str(error)}, ensure_ascii=False).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(audio)))
            self.end_headers()
            self.wfile.write(audio)

        def log_message(self, format: str, *args: object) -> None:
            print(f"{self.address_string()} {format % args}", file=sys.stderr)

    server = HTTPServer((args.host, args.port), Handler)
    print(f"listening on http://{args.host}:{args.port}/render", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models-dir", type=Path, default=DEFAULT_MODELS_DIR)
    parser.add_argument("--voice-map", help='例: "host=jvnv-F1-jp,learner=jvnv-M1-jp"')
    parser.add_argument("--device", default="cpu")
    subparsers = parser.add_subparsers(dest="command", required=True)

    download = subparsers.add_parser("download", help="JVNV の音声モデルを取得する")
    download.set_defaults(func=_cmd_download)

    render = subparsers.add_parser("render", help="1発話を WAV に書き出す")
    render.add_argument("--text", required=True)
    render.add_argument("--output", type=Path, required=True)
    render.add_argument("--speaker", default="host")
    render.add_argument("--emotion", default="neutral")
    render.add_argument("--speed", type=float, default=1.0)
    render.set_defaults(func=_cmd_render)

    serve = subparsers.add_parser("serve", help="WAV を返す HTTP エンドポイントを常駐させる")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)
    serve.set_defaults(func=_cmd_serve)

    args = parser.parse_args()
    try:
        return args.func(args)
    except StyleBertVITS2Error as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
