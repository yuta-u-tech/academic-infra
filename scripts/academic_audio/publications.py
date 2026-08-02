"""Persistent publication records, mirroring jobs.py.

`index.json` maps `audio_hash -> publication_id` so a re-run against the same
audio doesn't re-upload (重複投稿防止). Each publication also gets its own
`<id>.json` for `status` / `resume`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Publication:
    publication_id: str
    job_id: str
    audio_hash: str
    status: str  # "uploading" | "uploaded" | "failed"
    title: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    video_id: str | None = None
    url: str | None = None
    visibility: str | None = None
    playlist_id: str | None = None
    error: str | None = None
    # 失敗時に resume で使う。成功後は削除して None にする（保持方針: 動画は一時ファイル）。
    video_path: str | None = None
    background_path: str | None = None

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> "Publication":
        return cls(**data)


def publications_dir(state_dir: Path) -> Path:
    return state_dir / "publications"


def _record_path(state_dir: Path, publication_id: str) -> Path:
    return publications_dir(state_dir) / f"{publication_id}.json"


def _index_path(state_dir: Path) -> Path:
    return publications_dir(state_dir) / "index.json"


def _read_index(state_dir: Path) -> dict[str, str]:
    path = _index_path(state_dir)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_index(state_dir: Path, index: dict[str, str]) -> None:
    path = _index_path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def find_by_audio_hash(state_dir: Path, audio_hash: str) -> Publication | None:
    publication_id = _read_index(state_dir).get(audio_hash)
    if publication_id is None:
        return None
    return read_publication(state_dir, publication_id)


def write_publication(state_dir: Path, publication: Publication) -> Path:
    path = _record_path(state_dir, publication.publication_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(publication.to_json_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    index = _read_index(state_dir)
    index[publication.audio_hash] = publication.publication_id
    _write_index(state_dir, index)
    return path


def read_publication(state_dir: Path, publication_id: str) -> Publication:
    path = _record_path(state_dir, publication_id)
    if not path.exists():
        raise FileNotFoundError(f"{path} がありません。")
    return Publication.from_json_dict(json.loads(path.read_text(encoding="utf-8")))
