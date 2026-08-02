"""Turn an AudioArtifact into an MP4 that YouTube will accept.

ffmpeg on this machine is built without `drawtext` (no fontconfig/freetype), so
the title card is rendered as a PNG with Pillow first, then muxed with the audio.
"""

from __future__ import annotations

import subprocess
import wave
from pathlib import Path

from .artifact import AudioArtifact

WIDTH = 1280
HEIGHT = 720
_BACKGROUND = (26, 26, 46)  # 濃紺。テキストが読める程度のコントラストを確保する
_FOREGROUND = (240, 240, 245)
_ACCENT = (130, 170, 255)

_LATIN_FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
)
# Arial 系は CJK グリフを持たず豆腐(□)になるため、日本語を含む場合はヒラギノに切り替える。
_CJK_FONT_CANDIDATES = (
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
)


class VideoError(Exception):
    pass


def render_background(title: str, subtitle: str, output_path: Path) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    has_cjk = any(_is_cjk(char) for char in f"{title}{subtitle}")
    font_title = _load_font(56, cjk=has_cjk)
    font_subtitle = _load_font(28, cjk=has_cjk)

    image = Image.new("RGB", (WIDTH, HEIGHT), _BACKGROUND)
    draw = ImageDraw.Draw(image)

    wrapped_title = _wrap(draw, title, font_title, WIDTH - 160)
    title_height = sum(_line_height(draw, line, font_title) for line in wrapped_title)
    subtitle_height = _line_height(draw, subtitle, font_subtitle) if subtitle else 0
    gap = 24 if subtitle else 0
    block_height = title_height + gap + subtitle_height
    y = (HEIGHT - block_height) / 2

    for line in wrapped_title:
        width = draw.textlength(line, font=font_title)
        draw.text(((WIDTH - width) / 2, y), line, font=font_title, fill=_FOREGROUND)
        y += _line_height(draw, line, font_title)
    if subtitle:
        y += gap
        width = draw.textlength(subtitle, font=font_subtitle)
        draw.text(((WIDTH - width) / 2, y), subtitle, font=font_subtitle, fill=_ACCENT)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return output_path


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x3000 <= code <= 0x30FF  # 句読点・ひらがな・カタカナ
        or 0x4E00 <= code <= 0x9FFF  # CJK統合漢字
        or 0xFF00 <= code <= 0xFFEF  # 全角英数
    )


def _load_font(size: int, *, cjk: bool):
    from PIL import ImageFont

    candidates = _CJK_FONT_CANDIDATES if cjk else _LATIN_FONT_CANDIDATES
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default(size=size)


def _line_height(draw, text: str, font) -> int:
    box = draw.textbbox((0, 0), text or " ", font=font)
    return int((box[3] - box[1]) * 1.35)


def _wrap(draw, text: str, font, max_width: float) -> list[str]:
    words = text.split()
    if not words:
        return [text]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines[:4]  # 4行を超える長い題名は切る。動画では要点だけ分かればよい


def build_mp4(audio_path: Path, background_path: Path, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        duration = _wav_seconds(audio_path)
    except (OSError, wave.Error) as error:
        raise VideoError(f"{audio_path} を読めません: {error}") from error
    command = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(background_path),
        "-i",
        str(audio_path),
        "-c:v",
        "libx264",
        "-tune",
        "stillimage",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        # -shortest だと、-loop 1 の静止画入力とのマルチプレクス時にコンテナの video
        # duration が実際の音声より数秒長く記録されることがある（moov 側の丸め）。
        # 音声の実尺を明示的に -t で切ることで、動画時間を音声と正確に一致させる。
        "-t",
        f"{duration:.3f}",
        str(output_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0 or not output_path.exists():
        raise VideoError(f"ffmpeg が失敗しました:\n{completed.stderr[-2000:]}")
    return output_path


def _wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / handle.getframerate()


def build_video(artifact: AudioArtifact, out_dir: Path) -> tuple[Path, Path]:
    """Render the background PNG and mux it with the artifact's audio. Returns (mp4, png)."""
    background_path = out_dir / "background.png"
    video_path = out_dir / "video.mp4"
    render_background(artifact.title, artifact.source_id, background_path)
    build_mp4(Path(artifact.audio_path), background_path, video_path)
    return video_path, background_path
