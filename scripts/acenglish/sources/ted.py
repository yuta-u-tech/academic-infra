"""TED / YouTube の字幕を取り込む。

`listening-materials/DESIGN.md` の方針をそのまま踏襲する: **音声はダウンロードしない**
（教材を解く間は元動画を TED/YouTube 側で見れば足りる）。`yt-dlp` で字幕だけを取り、
文単位に正規化する。ここは判断の要らない機械的な変換なので決定論コードでよい。

faster-whisper へのフォールバックは作らない（同 DESIGN の判断。TED はほぼ 100% 字幕がある）。
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .base import ExternalMaterial, note_path_for, slugify

_TIMEOUT_SECONDS = 180
# 優先順: 手動字幕(en) → 自動字幕。手動の方がタイムスタンプも表記も整っている。
_SUBTITLE_LANGS = "en,en-US,en-GB"
_TIMESTAMP_LINE = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s+-->")
_VTT_TAG = re.compile(r"<[^>]+>")


class SubtitleNotFoundError(Exception):
    pass


class YtDlpNotInstalledError(Exception):
    pass


@dataclass(frozen=True)
class Talk:
    title: str
    url: str
    uploader: str
    sentences: list[str]

    @property
    def body(self) -> str:
        return "\n".join(self.sentences)


def _run_yt_dlp(arguments: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["yt-dlp", *arguments], capture_output=True, text=True, timeout=_TIMEOUT_SECONDS
        )
    except FileNotFoundError as error:
        raise YtDlpNotInstalledError(
            "yt-dlp が見つかりません。`python3 -m pip install yt-dlp` を実行してください。"
        ) from error


def parse_vtt(vtt: str) -> list[str]:
    """WebVTT を文の並びに直す。

    自動字幕は同じ行を送り出しながら重複して出す（カラオケ表示のため）ので、
    直前と同じ行は捨てる。これをやらないと同じ文が何度も教材に入る。
    """
    lines: list[str] = []
    for raw in vtt.splitlines():
        line = _VTT_TAG.sub("", html.unescape(raw)).strip()
        if not line or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            continue
        if _TIMESTAMP_LINE.match(line) or line.isdigit():
            continue
        if lines and lines[-1] == line:
            continue
        lines.append(line)

    text = re.sub(r"\s+", " ", " ".join(lines)).strip()
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'])", text)
    return [s.strip() for s in sentences if s.strip()]


def fetch_talk(url: str) -> Talk:
    """字幕のみ取得する（`--skip-download`）。音声・動画は落とさない。"""
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "talk"
        result = _run_yt_dlp(
            [
                "--skip-download",
                "--write-subs",
                "--write-auto-subs",
                "--sub-langs",
                _SUBTITLE_LANGS,
                "--sub-format",
                "vtt",
                "--write-info-json",
                "--output",
                str(output),
                url,
            ]
        )
        subtitles = sorted(Path(directory).glob("*.vtt"))
        if not subtitles:
            raise SubtitleNotFoundError(
                f"{url} から英語字幕を取得できませんでした。\n{result.stderr.strip()[:400]}"
            )

        sentences = parse_vtt(subtitles[0].read_text(encoding="utf-8"))
        info_files = sorted(Path(directory).glob("*.info.json"))
        info = json.loads(info_files[0].read_text(encoding="utf-8")) if info_files else {}

    if not sentences:
        raise SubtitleNotFoundError(f"{url} の字幕が空でした。")
    return Talk(
        title=info.get("title") or url,
        url=info.get("webpage_url") or url,
        uploader=info.get("uploader") or "",
        sentences=sentences,
    )


def to_material(talk: Talk, max_sentences: int = 60) -> ExternalMaterial:
    """1トークを1つの学習対象にする。

    長いトークをそのまま渡すと生成側が要約に流れて教材にならないので、先頭から
    `max_sentences` 文で切る。続きが要るときは同じトークをもう一度、別の範囲で取る。
    """
    return ExternalMaterial(
        review_id=f"ted.{slugify(talk.title)}",
        source="ted",
        title=talk.title,
        body="\n".join(talk.sentences[:max_sentences]),
        origin=talk.url,
        source_file=note_path_for("listening", "ted"),
        source_commit=slugify(talk.title),
        chapter_title=talk.uploader or "TED",
    )
