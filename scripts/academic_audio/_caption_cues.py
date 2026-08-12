"""字幕cueの文分割ヘルパー。Part5/リスニング(Part2/3/4)全テンプレート共通。

長い解説を1つのcueにまとめると、字幕ボックスに収まりきらない
(2026-08-12「字幕が大きくなりすぎている」の指摘の直接原因)。文単位に分割して
文字数比例で時間を割ることで、常に読める分量のcueにする。
"""

from __future__ import annotations

import re

EN_SENTENCE_SPLIT = re.compile(r"(?<=[.!?]) ")
JA_SENTENCE_SPLIT = re.compile(r"(?<=。)")


def sentence_cues(text: str, duration: float, split_pattern: re.Pattern, offset: float = 0.0) -> list[dict]:
    """音声そのものと1対1で対応しない字幕(日本語訳等)にも使うため、厳密な同期では
    なく近似でよい前提。"""
    sentences = [s.strip() for s in split_pattern.split(text) if s.strip()]
    if not sentences:
        return [{"start": round(offset, 3), "end": round(offset + duration, 3), "text": text.strip()}]
    total_chars = sum(len(s) for s in sentences) or 1
    cues = []
    cursor = offset
    for sentence in sentences:
        span = duration * (len(sentence) / total_chars)
        cues.append({"start": round(cursor, 3), "end": round(cursor + span, 3), "text": sentence})
        cursor += span
    return cues
