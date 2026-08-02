from __future__ import annotations

from pathlib import Path

import pytest

from academic_audio.publications import Publication, find_by_audio_hash, read_publication, write_publication


def _publication(**overrides) -> Publication:
    defaults = dict(publication_id="pub-1", job_id="job-1", audio_hash="a" * 64, status="uploaded")
    defaults.update(overrides)
    return Publication(**defaults)


def test_write_then_read_round_trips(tmp_path: Path) -> None:
    write_publication(tmp_path, _publication(title="t", video_id="v1", url="https://youtu.be/v1"))

    record = read_publication(tmp_path, "pub-1")

    assert record.status == "uploaded"
    assert record.video_id == "v1"
    assert record.tags == []  # 既定は空配列（None ではない）


def test_read_missing_publication_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_publication(tmp_path, "does-not-exist")


def test_find_by_audio_hash_locates_the_publication(tmp_path: Path) -> None:
    write_publication(tmp_path, _publication(audio_hash="deadbeef"))

    found = find_by_audio_hash(tmp_path, "deadbeef")

    assert found is not None
    assert found.publication_id == "pub-1"


def test_find_by_audio_hash_returns_none_when_unknown(tmp_path: Path) -> None:
    assert find_by_audio_hash(tmp_path, "never-seen") is None


def test_write_updates_the_index_on_status_change(tmp_path: Path) -> None:
    write_publication(tmp_path, _publication(status="uploading"))
    write_publication(tmp_path, _publication(status="uploaded", video_id="v1"))

    found = find_by_audio_hash(tmp_path, "a" * 64)

    assert found is not None
    assert found.status == "uploaded"
    assert found.video_id == "v1"
