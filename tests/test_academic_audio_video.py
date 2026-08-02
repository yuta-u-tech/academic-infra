from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from academic_audio.artifact import AudioArtifact
from academic_audio.video import VideoError, _is_cjk, build_mp4, build_video, render_background

try:
    import PIL  # noqa: F401

    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or not _HAS_PIL, reason="ffmpeg または Pillow が無い"
)


def _write_silent_wav(path: Path, seconds: float = 1.0, sample_rate: int = 22050) -> Path:
    frames = int(sample_rate * seconds)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * frames)
    return path


def test_is_cjk_detects_japanese_but_not_ascii() -> None:
    assert _is_cjk("真")
    assert _is_cjk("ノ")
    assert not _is_cjk("A")
    assert not _is_cjk("3")


def test_render_background_produces_an_image(tmp_path: Path) -> None:
    output = render_background("真理値表 リスニング（TOEIC Part 3 形式）", "logic.ch01.s01", tmp_path / "bg.png")

    assert output.exists()
    assert output.stat().st_size > 0


def test_render_background_wraps_a_long_english_title(tmp_path: Path) -> None:
    # 折り返しが機能しないと画面外にはみ出す。ここでは例外を起こさず生成できることだけ確認する
    # （実際の折り返し結果はビジュアル確認済み: background3.png）。
    output = render_background("A" * 5 + " " + "B" * 5 + " " + "C" * 5 + " " * 1 + "D" * 5, "sub", tmp_path / "bg.png")
    assert output.exists()


def test_build_mp4_matches_the_audio_duration(tmp_path: Path) -> None:
    audio = _write_silent_wav(tmp_path / "audio.wav", seconds=1.0)
    background = render_background("Test", "sub", tmp_path / "bg.png")

    video_path = build_mp4(audio, background, tmp_path / "video.mp4")

    assert video_path.exists()
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "csv=p=0", str(video_path)],
        capture_output=True, text=True,
    )
    durations = {}
    for line in probe.stdout.strip().splitlines():
        codec_type, duration = line.split(",")
        durations[codec_type] = float(duration)
    # -shortest だとコンテナの video duration が音声より数秒長くなる不具合があったため、
    # -t で明示的に切っている。ここが崩れると再び動画が音声より長い「無音の静止フレーム」を持つ。
    assert durations["video"] == pytest.approx(durations["audio"], abs=0.1)
    assert durations["audio"] == pytest.approx(1.0, abs=0.1)


def test_build_mp4_reports_ffmpeg_failure(tmp_path: Path) -> None:
    missing_audio = tmp_path / "does-not-exist.wav"
    background = render_background("Test", "sub", tmp_path / "bg.png")

    with pytest.raises(VideoError):
        build_mp4(missing_audio, background, tmp_path / "video.mp4")


def test_build_video_from_an_artifact(tmp_path: Path) -> None:
    audio = _write_silent_wav(tmp_path / "output.wav", seconds=0.5)
    artifact = AudioArtifact(
        job_id="job-1", title="Test Video", source_id="logic.ch01.s01", source_commit="abc123",
        engine="wav", mode="fast", audio_path=str(audio), duration=0.5, sample_rate=22050, channels=1,
        script_hash="a" * 64, audio_hash="b" * 64, source_hash="c" * 64,
    )

    video_path, background_path = build_video(artifact, tmp_path / "out")

    assert video_path.exists()
    assert background_path.exists()
