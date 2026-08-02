"""Pull vocabulary terms from `yuta-u-tech/study-forge` to seed listening items.

`acenglish/sources/studyforge.py` は同じデータをもっと深く取り込む（1語1教材にし、
例文を分割し、生成パイプラインに渡す）が、それは `..items`（pydantic 依存）を
import する。ここでは作問プロンプトに数語添えるだけなので、その依存を引きずらない
よう、生の fetch だけを独立して持つ。
"""

from __future__ import annotations

import json
import random
import urllib.error
import urllib.request

REPOSITORY = "yuta-u-tech/study-forge"
_RAW_BASE = f"https://raw.githubusercontent.com/{REPOSITORY}/HEAD/data"
_TIMEOUT_SECONDS = 30

DECKS = (
    "words1-400",
    "words401-700",
    "words701-900",
    "words901-1000",
    "supplement1",
    "supplement2",
    "supplement3",
)


class VocabFetchError(Exception):
    pass


def sample_terms(deck: str, count: int, *, seed: int | None = None) -> list[dict]:
    """Fetch `deck` and return `count` random {term, definition, example} entries."""
    if deck not in DECKS:
        raise VocabFetchError(f"未知のデッキ '{deck}'（対応: {', '.join(DECKS)}）")
    request = urllib.request.Request(f"{_RAW_BASE}/{deck}.json", headers={"User-Agent": "academic-audio/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310 - 固定のhttps
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as error:
        raise VocabFetchError(f"{deck} を取得できません: {error}") from error
    terms = data.get("terms") or []
    if not terms:
        raise VocabFetchError(f"{deck} に語彙がありません。")
    rng = random.Random(seed)
    return rng.sample(terms, k=min(count, len(terms)))
