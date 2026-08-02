"""AudioArtifact → YouTube（限定公開）。Issue #3 の Publisher 抽象化。

```python
class AudioPublisher(Protocol):
    def health_check(self) -> None: ...
    def publish(self, artifact: AudioArtifact) -> PublishResult: ...
    def get_status(self, publication_id: str) -> PublishStatus: ...
```

初期対象は YouTubePublisher。LocalPublisher はテスト・オフライン確認用（動画化までは
本番と同じコードパスを通し、アップロードだけ行わない）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .artifact import AudioArtifact
from .metadata import describe
from .publications import Publication, find_by_audio_hash, read_publication, write_publication
from .video import VideoError, build_video

DEFAULT_VISIBILITY = "unlisted"  # 受け入れ条件: 既定の公開範囲は限定公開に固定する
_CATEGORY_EDUCATION = "27"
_RETRYABLE_HTTP_STATUS = (500, 502, 503, 504)
_MAX_UPLOAD_RETRIES = 5


class PublishError(Exception):
    pass


@dataclass(frozen=True)
class PublishResult:
    publication_id: str
    status: str  # "uploaded" | "duplicate" | "dry_run"
    video_id: str | None
    url: str | None
    visibility: str | None


@dataclass(frozen=True)
class PublishStatus:
    publication_id: str
    status: str  # "uploading" | "uploaded" | "failed"
    video_id: str | None
    url: str | None
    error: str | None


class AudioPublisher(Protocol):
    def health_check(self) -> None: ...
    def publish(self, artifact: AudioArtifact, *, dry_run: bool = False, force: bool = False) -> PublishResult: ...
    def get_status(self, publication_id: str) -> PublishStatus: ...


class YouTubePublisher:
    def __init__(
        self,
        *,
        state_dir: Path,
        credentials: dict[str, str],
        visibility: str = DEFAULT_VISIBILITY,
        playlist_id: str | None = None,
    ):
        import _youtube_common

        self.state_dir = state_dir
        self.visibility = visibility
        self.playlist_id = playlist_id
        self._credentials = credentials
        self._service = None

    @property
    def service(self):
        import _youtube_common

        if self._service is None:
            self._service = _youtube_common.build_service(self._credentials)
        return self._service

    def health_check(self) -> None:
        try:
            self.service.channels().list(part="id", mine=True).execute()
        except Exception as error:  # googleapiclient は多様な例外を投げる
            raise PublishError(f"YouTube API に接続できません: {error}") from error

    def publish(self, artifact: AudioArtifact, *, dry_run: bool = False, force: bool = False, keep_video: bool = False) -> PublishResult:
        existing = find_by_audio_hash(self.state_dir, artifact.audio_hash)
        if existing and existing.status == "uploaded" and not force:
            # 重複投稿防止。同じ音声(hash一致)は再アップロードせず既存の video を返す。
            return PublishResult(
                publication_id=existing.publication_id, status="duplicate",
                video_id=existing.video_id, url=existing.url, visibility=existing.visibility,
            )

        metadata = describe(artifact)
        publication_id = existing.publication_id if existing else artifact.job_id
        if dry_run:
            return PublishResult(publication_id=publication_id, status="dry_run", video_id=None, url=None, visibility=self.visibility)

        record = Publication(
            publication_id=publication_id, job_id=artifact.job_id, audio_hash=artifact.audio_hash,
            status="uploading", title=metadata.title, description=metadata.description, tags=metadata.tags,
            visibility=self.visibility, playlist_id=self.playlist_id,
        )
        write_publication(self.state_dir, record)

        out_dir = Path(artifact.audio_path).parent / "video"
        try:
            video_path, background_path = build_video(artifact, out_dir)
        except VideoError as error:
            record.status, record.error = "failed", str(error)
            write_publication(self.state_dir, record)
            raise PublishError(str(error)) from error
        record.video_path, record.background_path = str(video_path), str(background_path)
        write_publication(self.state_dir, record)

        return self._upload_and_finalize(record, video_path, background_path, keep_video=keep_video)

    def resume(self, publication_id: str, *, keep_video: bool = False) -> PublishResult:
        """途中で失敗した投稿を、動画の作り直しなしで再送する。

        HTTP のバイト単位レジュームではなく、ローカルに残っている動画ファイルから
        アップロードをやり直す形。動画生成（ffmpeg/Pillow）を再実行しない分だけ速い。
        """
        record = read_publication(self.state_dir, publication_id)
        if record.status == "uploaded":
            return PublishResult(
                publication_id=publication_id, status="duplicate",
                video_id=record.video_id, url=record.url, visibility=record.visibility,
            )
        if not record.video_path or not Path(record.video_path).exists():
            raise PublishError(
                f"{publication_id} の動画ファイルが残っていません。listening ingest / render からやり直してください。"
            )
        background_path = Path(record.background_path) if record.background_path and Path(record.background_path).exists() else None
        return self._upload_and_finalize(record, Path(record.video_path), background_path, keep_video=keep_video)

    def get_status(self, publication_id: str) -> PublishStatus:
        record = read_publication(self.state_dir, publication_id)
        return PublishStatus(
            publication_id=record.publication_id, status=record.status,
            video_id=record.video_id, url=record.url, error=record.error,
        )

    def _upload_and_finalize(
        self, record: Publication, video_path: Path, background_path: Path | None, *, keep_video: bool
    ) -> PublishResult:
        try:
            video_id = self._upload(video_path, record)
            if background_path is not None:
                self._set_thumbnail(video_id, background_path)
            if record.playlist_id:
                self._add_to_playlist(video_id, record.playlist_id)
        except PublishError as error:
            record.status, record.error = "failed", str(error)
            write_publication(self.state_dir, record)
            raise

        record.status, record.video_id, record.url, record.error = "uploaded", video_id, f"https://youtu.be/{video_id}", None
        if not keep_video:
            # 保持方針: 動画はアップロード後の一時ファイル。音声・台本の正本は別にある。
            video_path.unlink(missing_ok=True)
            if background_path is not None:
                background_path.unlink(missing_ok=True)
            record.video_path, record.background_path = None, None
        write_publication(self.state_dir, record)
        return PublishResult(publication_id=record.publication_id, status="uploaded", video_id=video_id, url=record.url, visibility=record.visibility)

    def _upload(self, video_path: Path, record: Publication) -> str:
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload

        body = {
            "snippet": {"title": record.title, "description": record.description, "tags": record.tags, "categoryId": _CATEGORY_EDUCATION},
            "status": {"privacyStatus": record.visibility, "selfDeclaredMadeForKids": False},
        }
        media = MediaFileUpload(str(video_path), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
        request = self.service.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        attempt = 0
        while response is None:
            try:
                _, response = request.next_chunk()
            except HttpError as error:
                status = getattr(error.resp, "status", None)
                if status in _RETRYABLE_HTTP_STATUS and attempt < _MAX_UPLOAD_RETRIES:
                    attempt += 1
                    time.sleep(min(2**attempt, 30))
                    continue
                raise PublishError(f"アップロードに失敗しました: {error}") from error
        return response["id"]

    def _set_thumbnail(self, video_id: str, background_path: Path) -> None:
        from googleapiclient.http import MediaFileUpload

        media = MediaFileUpload(str(background_path), mimetype="image/png")
        self.service.thumbnails().set(videoId=video_id, media_body=media).execute()

    def _add_to_playlist(self, video_id: str, playlist_id: str) -> None:
        body = {"snippet": {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}
        self.service.playlistItems().insert(part="snippet", body=body).execute()


class LocalPublisher:
    """ネットワークに触らない Publisher。動画化までは本番と同じコードパスを通す。

    YouTube 認証が無くても、メタデータ・動画生成・重複判定・resume の挙動を
    確認できるようにするためのもの（テスト、オフラインでの動作確認）。
    """

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir

    def health_check(self) -> None:
        return None

    def publish(self, artifact: AudioArtifact, *, dry_run: bool = False, force: bool = False, keep_video: bool = True) -> PublishResult:
        existing = find_by_audio_hash(self.state_dir, artifact.audio_hash)
        if existing and existing.status == "uploaded" and not force:
            return PublishResult(publication_id=existing.publication_id, status="duplicate", video_id=existing.video_id, url=existing.url, visibility="local")

        metadata = describe(artifact)
        if dry_run:
            return PublishResult(publication_id=artifact.job_id, status="dry_run", video_id=None, url=None, visibility="local")

        out_dir = Path(artifact.audio_path).parent / "video"
        video_path, background_path = build_video(artifact, out_dir)
        video_id = f"local-{artifact.audio_hash[:12]}"
        record = Publication(
            publication_id=artifact.job_id, job_id=artifact.job_id, audio_hash=artifact.audio_hash,
            status="uploaded", title=metadata.title, description=metadata.description, tags=metadata.tags,
            visibility="local", video_id=video_id, url=str(video_path),
            video_path=str(video_path), background_path=str(background_path),
        )
        write_publication(self.state_dir, record)
        return PublishResult(publication_id=record.publication_id, status="uploaded", video_id=video_id, url=str(video_path), visibility="local")

    def get_status(self, publication_id: str) -> PublishStatus:
        record = read_publication(self.state_dir, publication_id)
        return PublishStatus(publication_id=record.publication_id, status=record.status, video_id=record.video_id, url=record.url, error=record.error)
