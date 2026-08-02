from __future__ import annotations

import shutil
import wave
from pathlib import Path

import pytest

from academic_audio.artifact import AudioArtifact
from academic_audio.publications import read_publication
from academic_audio.publisher import (
    DEFAULT_VISIBILITY,
    LocalPublisher,
    PublishError,
    YouTubePublisher,
)

try:
    import PIL  # noqa: F401

    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or not _HAS_PIL, reason="ffmpeg または Pillow が無い"
)


def _write_silent_wav(path: Path, seconds: float = 0.3, sample_rate: int = 22050) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(sample_rate * seconds)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * frames)
    return path


def _artifact(tmp_path: Path, *, audio_hash: str = "hash-1", job_id: str = "job-1") -> AudioArtifact:
    audio = _write_silent_wav(tmp_path / job_id / "output.wav")
    return AudioArtifact(
        job_id=job_id, title="Test Audio", source_id="logic.ch01.s01", source_commit="abc123",
        engine="wav", mode="fast", audio_path=str(audio), duration=0.3, sample_rate=22050, channels=1,
        script_hash="a" * 64, audio_hash=audio_hash, source_hash="c" * 64,
    )


# --- LocalPublisher: 実際に ffmpeg を通す（YouTube には触れない） ------------------------


def test_local_publisher_dry_run_builds_nothing(tmp_path: Path) -> None:
    publisher = LocalPublisher(state_dir=tmp_path / "state")
    artifact = _artifact(tmp_path)

    result = publisher.publish(artifact, dry_run=True)

    assert result.status == "dry_run"
    assert not (Path(artifact.audio_path).parent / "video").exists()


def test_local_publisher_publishes_and_dedups(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    publisher = LocalPublisher(state_dir=state_dir)
    artifact = _artifact(tmp_path)

    first = publisher.publish(artifact)
    assert first.status == "uploaded"
    assert Path(first.url).exists()

    second = publisher.publish(artifact)
    assert second.status == "duplicate"
    assert second.video_id == first.video_id


def test_local_publisher_force_republishes(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    publisher = LocalPublisher(state_dir=state_dir)
    artifact = _artifact(tmp_path)
    first = publisher.publish(artifact)

    second = publisher.publish(artifact, force=True)

    assert second.status == "uploaded"


def test_local_publisher_get_status(tmp_path: Path) -> None:
    publisher = LocalPublisher(state_dir=tmp_path / "state")
    artifact = _artifact(tmp_path)
    published = publisher.publish(artifact)

    status = publisher.get_status(published.publication_id)

    assert status.status == "uploaded"
    assert status.video_id == published.video_id


# --- YouTubePublisher: googleapiclient をモックして、ネットワークに触れず検証する -----------


def _http_error(status: int):
    # publisher._upload() は googleapiclient.errors.HttpError だけを retry 対象として
    # 拾うので、独自の例外クラスではなく本物を使う必要がある。
    from googleapiclient.errors import HttpError

    response = type("Response", (), {"status": status, "reason": "error"})()
    return HttpError(response, b"{}", uri="https://example.invalid")


class _FakeInsertRequest:
    """videos().insert(...) が返すオブジェクトの代役。next_chunk() を N 回呼ぶと完了する。"""

    def __init__(self, video_id: str, *, fail_times: int = 0, fail_status: int = 503):
        self.video_id = video_id
        self._remaining_failures = fail_times
        self._fail_status = fail_status
        self.calls = 0

    def next_chunk(self):
        self.calls += 1
        if self._remaining_failures > 0:
            self._remaining_failures -= 1
            raise _http_error(self._fail_status)
        return None, {"id": self.video_id}


class _FakeExecutable:
    def __init__(self, result=None, *, raises: Exception | None = None):
        self._result = result
        self._raises = raises
        self.called_with: dict | None = None

    def execute(self):
        if self._raises:
            raise self._raises
        return self._result


class _FakeYouTubeService:
    def __init__(self, *, video_id: str = "abc123", fail_times: int = 0, health_error: Exception | None = None):
        self.video_id = video_id
        self.fail_times = fail_times
        self.health_error = health_error
        self.uploaded_bodies: list[dict] = []
        self.thumbnails_set: list[str] = []
        self.playlist_inserts: list[dict] = []

    def channels(self):
        return self

    def list(self, **kwargs):
        return _FakeExecutable({"items": [{"id": "channel-1"}]}, raises=self.health_error)

    def videos(self):
        return self

    def thumbnails(self):
        return self

    def set(self, videoId, media_body):
        self.thumbnails_set.append(videoId)
        return _FakeExecutable({})

    def playlistItems(self):
        self._next_insert_is_playlist = True
        return self

    def insert(self, part, body, media_body=None):
        # videos() と playlistItems() は同じ self を返すので、直前にどちらを
        # 経由したかで振り分ける（実際の googleapiclient は別オブジェクトを返すが、
        # ここではフェイクを簡潔にするためこの形にしている）。
        if getattr(self, "_next_insert_is_playlist", False):
            self._next_insert_is_playlist = False
            self.playlist_inserts.append(body)
            return _FakeExecutable({})
        self.uploaded_bodies.append(body)
        return _FakeInsertRequest(self.video_id, fail_times=self.fail_times)


def _publisher(tmp_path: Path, service: _FakeYouTubeService, **kwargs) -> YouTubePublisher:
    publisher = YouTubePublisher(
        state_dir=tmp_path / "state",
        credentials={"YOUTUBE_OAUTH_CLIENT_ID": "x", "YOUTUBE_OAUTH_CLIENT_SECRET": "y", "YOUTUBE_OAUTH_REFRESH_TOKEN": "z"},
        **kwargs,
    )
    publisher._service = service  # build_service() を経由させず、直接差し込む
    return publisher


def test_youtube_publisher_health_check_passes(tmp_path: Path) -> None:
    publisher = _publisher(tmp_path, _FakeYouTubeService())
    publisher.health_check()  # 例外が出なければ良い


def test_youtube_publisher_health_check_fails_loudly(tmp_path: Path) -> None:
    publisher = _publisher(tmp_path, _FakeYouTubeService(health_error=RuntimeError("boom")))

    with pytest.raises(PublishError):
        publisher.health_check()


def test_youtube_publisher_uploads_with_unlisted_by_default(tmp_path: Path) -> None:
    service = _FakeYouTubeService(video_id="vid-1")
    publisher = _publisher(tmp_path, service)
    artifact = _artifact(tmp_path)

    result = publisher.publish(artifact)

    assert result.status == "uploaded"
    assert result.video_id == "vid-1"
    assert result.url == "https://youtu.be/vid-1"
    assert result.visibility == DEFAULT_VISIBILITY
    assert service.uploaded_bodies[0]["status"]["privacyStatus"] == "unlisted"
    assert service.thumbnails_set == ["vid-1"]


def test_youtube_publisher_deletes_the_local_video_after_upload(tmp_path: Path) -> None:
    publisher = _publisher(tmp_path, _FakeYouTubeService())
    artifact = _artifact(tmp_path)

    publisher.publish(artifact)

    record = read_publication(tmp_path / "state", artifact.job_id)
    assert record.video_path is None  # 保持方針: アップロード後は消す


def test_youtube_publisher_keeps_the_video_when_asked(tmp_path: Path) -> None:
    publisher = _publisher(tmp_path, _FakeYouTubeService())
    artifact = _artifact(tmp_path)

    publisher.publish(artifact, keep_video=True)

    record = read_publication(tmp_path / "state", artifact.job_id)
    assert record.video_path is not None
    assert Path(record.video_path).exists()


def test_youtube_publisher_dedups_by_audio_hash(tmp_path: Path) -> None:
    service = _FakeYouTubeService(video_id="vid-1")
    publisher = _publisher(tmp_path, service)
    artifact = _artifact(tmp_path)
    publisher.publish(artifact)

    second = publisher.publish(artifact)

    assert second.status == "duplicate"
    assert len(service.uploaded_bodies) == 1  # 2回目はアップロードされていない


def test_youtube_publisher_adds_to_the_playlist_when_configured(tmp_path: Path) -> None:
    service = _FakeYouTubeService(video_id="vid-1")
    publisher = _publisher(tmp_path, service, playlist_id="PL123")
    artifact = _artifact(tmp_path)

    result = publisher.publish(artifact)

    assert result.status == "uploaded"
    assert service.playlist_inserts == [{"snippet": {"playlistId": "PL123", "resourceId": {"kind": "youtube#video", "videoId": "vid-1"}}}]


def test_youtube_publisher_retries_on_5xx_then_succeeds(tmp_path: Path, monkeypatch) -> None:
    from academic_audio import publisher as publisher_module

    monkeypatch.setattr(publisher_module.time, "sleep", lambda seconds: None)
    service = _FakeYouTubeService(video_id="vid-1", fail_times=2)
    publisher = _publisher(tmp_path, service)
    artifact = _artifact(tmp_path)

    result = publisher.publish(artifact)

    assert result.status == "uploaded"


def test_youtube_publisher_gives_up_after_too_many_5xx(tmp_path: Path, monkeypatch) -> None:
    from academic_audio import publisher as publisher_module

    monkeypatch.setattr(publisher_module.time, "sleep", lambda seconds: None)
    service = _FakeYouTubeService(video_id="vid-1", fail_times=99)
    publisher = _publisher(tmp_path, service)
    artifact = _artifact(tmp_path)

    with pytest.raises(PublishError):
        publisher.publish(artifact)

    record = read_publication(tmp_path / "state", artifact.job_id)
    assert record.status == "failed"
    assert record.video_path is not None  # 失敗時は resume できるよう動画を残す


def test_youtube_publisher_resume_uploads_the_kept_video_without_rebuilding(tmp_path: Path, monkeypatch) -> None:
    from academic_audio import publisher as publisher_module

    service = _FakeYouTubeService(video_id="vid-1")
    publisher = _publisher(tmp_path, service)
    artifact = _artifact(tmp_path)
    publisher.publish(artifact, keep_video=True)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("resume は動画を作り直さないはず")

    monkeypatch.setattr(publisher_module, "build_video", _fail_if_called)

    # 実際は publish() 成功時点で status=uploaded になっているので、故意に failed へ戻して検証する。
    from academic_audio.publications import read_publication, write_publication

    record = read_publication(tmp_path / "state", artifact.job_id)
    record.status, record.error = "failed", "simulated network error"
    write_publication(tmp_path / "state", record)

    result = publisher.resume(artifact.job_id)

    assert result.status == "uploaded"


def test_youtube_publisher_resume_without_a_local_video_fails_clearly(tmp_path: Path) -> None:
    service = _FakeYouTubeService(video_id="vid-1")
    publisher = _publisher(tmp_path, service)
    artifact = _artifact(tmp_path)
    publisher.publish(artifact, keep_video=False)  # 動画は削除済み

    from academic_audio.publications import read_publication, write_publication

    record = read_publication(tmp_path / "state", artifact.job_id)
    record.status = "failed"
    write_publication(tmp_path / "state", record)

    with pytest.raises(PublishError, match="残っていません"):
        publisher.resume(artifact.job_id)
