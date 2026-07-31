"""Normalize text before TTS rendering."""

from __future__ import annotations

import re

_REPLACEMENTS = {
    "AI": "エーアイ",
    "CPU": "シーピーユー",
    "GPU": "ジーピーユー",
    "CLI": "シーエルアイ",
    "TTS": "ティーティーエス",
}


def normalize(text: str) -> str:
    normalized = text
    for key, value in _REPLACEMENTS.items():
        normalized = re.sub(rf"\b{re.escape(key)}\b", value, normalized)
    normalized = normalized.replace("→", "から")
    normalized = re.sub(r"`([^`]+)`", r"\1", normalized)
    normalized = re.sub(r"\$([^$]+)\$", r"\1", normalized)
    # 箇条書き記号と見出しの # は、そのまま「ハイフン」「シャープ」と読み上げられてしまう。
    normalized = re.sub(r"(?:(?<=^)|(?<=\s))[-*]\s+", "", normalized)
    normalized = re.sub(r"(?:(?<=^)|(?<=\s))#{1,6}\s+", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip()
