from __future__ import annotations

from academic_audio.artifact import AudioArtifact, Chapter
from academic_audio.metadata import _timestamp, describe


def _artifact(**overrides) -> AudioArtifact:
    defaults = dict(
        job_id="job-1",
        title="真理値表 リスニング",
        source_id="logic.ch01.s01",
        source_commit="abcdef1234567890",
        engine="piper",
        mode="fast",
        audio_path="/tmp/output.wav",
        duration=42.5,
        sample_rate=22050,
        channels=1,
        script_hash="a" * 64,
        audio_hash="b" * 64,
        source_hash="c" * 64,
        segments=[],
        chapters=[Chapter(item_id="item-001", start=0.0, end=10.0, title="第1問")],
    )
    defaults.update(overrides)
    return AudioArtifact(**defaults)


def test_describe_includes_source_and_engine() -> None:
    metadata = describe(_artifact())

    assert metadata.title == "真理値表 リスニング"
    assert "logic.ch01.s01" in metadata.description
    assert "abcdef123456" in metadata.description  # commit は短縮する
    assert "piper / fast" in metadata.description
    assert metadata.tags == ["academic-audio", "logic"]
    assert metadata.category_id == "27"


def test_describe_includes_chapters_when_the_first_starts_at_zero() -> None:
    metadata = describe(_artifact())

    assert "チャプター:" in metadata.description
    assert "0:00 第1問" in metadata.description


def test_describe_omits_chapters_when_the_first_does_not_start_at_zero() -> None:
    # YouTube はチャプターが認識されるために先頭が 0:00 である必要があるため、
    # そうでない場合は誤解を招くチャプター一覧を出さない。
    metadata = describe(_artifact(chapters=[Chapter(item_id="item-001", start=5.0, end=10.0, title="第1問")]))

    assert "チャプター:" not in metadata.description


def test_describe_truncates_an_overlong_title() -> None:
    metadata = describe(_artifact(title="あ" * 200))

    assert len(metadata.title) == 100
    assert metadata.title.endswith("...")


def test_timestamp_formats_with_and_without_hours() -> None:
    assert _timestamp(5) == "0:05"
    assert _timestamp(65) == "1:05"
    assert _timestamp(3665) == "1:01:05"
