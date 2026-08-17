"""金フレ(study-forge由来のTOEIC語彙DB)から、コロケーション暗記動画のスライド
一式を組み立てる。

コロケーションフレーズ自体はDBに元から無い(取り込み時点のVocabItem.collocationsは
常に空配列)ため、Claudeが1語ずつ書く(review_slides.pyのreason_en/pointsと同じ
役割分担)。書いたら`persist_collocations()`でgenerated_item.payloadへ書き戻し、
次回以降は再生成せず再利用する(2026-08-18、ユーザー方針)。

**全文を英語→日本語で読み上げる**(2026-08-18、寝ながら聞く用途のため画面を見なくても
内容が分かる必要があるという指摘で追加。それまでは英語ナレーションのみで日本語は
字幕だけだった)。単語→意味→(コロケーション→和訳)×N→例文→例文和訳の順に、
speaker="narrator_en"/"narrator_ja"を切り替えながら1つずつ音声を作り、
`--piper-voice-map narrator_en=<英語モデル>,narrator_ja=<日本語モデル>`で
2モデルを渡す(MultiSpeakerPiperEngineの話者ディスパッチをそのまま流用)。

1語 = 1枚のスライド(word/collocations/example)。復習動画のQuestion/Answer
2枚構成と違い、暗記のテンポを優先して1枚に収める。
"""

from __future__ import annotations

import json
import sqlite3
import wave
from pathlib import Path

from .engines import TTSEngine
from .models import DialogueSegment
from .pronunciation import normalize
from .renderer import concatenate_wav

# 単語/意味の後、コロケーション同士の間は「間が無く詰まって聞こえる」という指摘
# (2026-08-18)への対応でやや長めに取る。例文前後は通常のギャップ。
_GAP_SECONDS = 0.45
_COLLOCATION_GAP_SECONDS = 0.9
_SLIDE_TAIL_SECONDS = 2.5

_REQUIRED_CONTENT_FIELDS = ("collocations", "example_en", "example_ja")


class CollocationSlideError(ValueError):
    pass


def _wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / handle.getframerate()


def persist_collocations(connection: sqlite3.Connection, review_id: str, collocations: list[dict]) -> None:
    """authored collocationsを generated_item.payload へ書き戻す(次回以降の再利用のため)。

    `collocations`: `[{"phrase": str, "phrase_ja": str}, ...]`。VocabItemの
    `collocations: list[str]`とは形が異なる(和訳も持たせたいため)ので、
    ここでは`collocations_v2`キーとして別に持つ(既存の`collocations`(空配列)は
    goigoi互換のため触らない)。
    """
    row = connection.execute(
        "SELECT payload FROM generated_item WHERE review_id = ?", (review_id,)
    ).fetchone()
    if row is None:
        raise CollocationSlideError(f"{review_id} が generated_item に見つかりません。")
    payload = json.loads(row[0])
    payload["collocations_v2"] = collocations
    connection.execute(
        "UPDATE generated_item SET payload = ? WHERE review_id = ?",
        (json.dumps(payload, ensure_ascii=False), review_id),
    )
    connection.commit()


def build_slides(
    items: list[dict],
    content_by_review_id: dict[str, dict],
    audio_dir: Path,
    engine: TTSEngine,
) -> list[dict]:
    """items: `[{review_id, word, meaning, part_of_speech}]`
    (material/generated_item から呼び出し側が組み立てる)。

    content_by_review_id: `{review_id: {collocations: [{"phrase": str, "phrase_ja": str}, ...]
    (1〜4個程度), example_en, example_ja}}`。`collocations`はDB
    (generated_item.payload.collocations_v2)にpersist済みならそれをそのまま詰め直す
    だけでよく、Claudeに書かせ直す必要はない(呼び出し側の責務)。
    """
    audio_dir.mkdir(parents=True, exist_ok=True)
    slides: list[dict] = []

    for row in items:
        review_id = row["review_id"]
        content = content_by_review_id.get(review_id)
        if content is None:
            raise CollocationSlideError(f"{review_id} の authored content がありません。")
        missing = [key for key in _REQUIRED_CONTENT_FIELDS if key not in content]
        if missing:
            raise CollocationSlideError(f"{review_id} の content に {', '.join(missing)} がありません。")

        word = row["word"]
        meaning = row["meaning"]
        collocations = content["collocations"]
        example_en = content["example_en"]
        example_ja = content["example_ja"]

        # (text, lang, gap_after)の順で発話ユニットを組み立てる。
        units: list[tuple[str, str, float]] = [(word, "en", _GAP_SECONDS), (meaning, "ja", _COLLOCATION_GAP_SECONDS)]
        for i, c in enumerate(collocations):
            is_last_collocation = i == len(collocations) - 1
            tail_gap = _GAP_SECONDS if not is_last_collocation else _COLLOCATION_GAP_SECONDS
            units.append((c["phrase"], "en", _GAP_SECONDS))
            units.append((c["phrase_ja"], "ja", _COLLOCATION_GAP_SECONDS if is_last_collocation else tail_gap))
        units.append((example_en, "en", _GAP_SECONDS))
        units.append((example_ja, "ja", 0.0))

        parts: list[Path] = []
        gaps: list[float] = []
        for i, (text, lang, gap) in enumerate(units):
            speaker = f"narrator_{lang}"
            out = audio_dir / f"{review_id}.u{i:02d}.{lang}.wav"
            engine.render(
                DialogueSegment(id=f"{review_id}.u{i:02d}", speaker=speaker, language=lang, text=normalize(text)),
                out,
            )
            parts.append(out)
            gaps.append(gap)

        merged = audio_dir / f"{review_id}.slide.wav"
        concatenate_wav(list(zip(parts, gaps)), merged)

        durations = [_wav_seconds(p) for p in parts]
        captions_en: list[dict] = []
        captions_ja: list[dict] = []
        cursor = 0.0
        for (text, lang, gap), duration in zip(units, durations):
            cue = {"start": round(cursor, 3), "end": round(cursor + duration, 3), "text": text}
            (captions_en if lang == "en" else captions_ja).append(cue)
            cursor += duration + gap

        total_duration = cursor + _SLIDE_TAIL_SECONDS

        slides.append(
            {
                "kind": "collocation",
                "reviewId": review_id,
                "word": word,
                "meaning": meaning,
                "partOfSpeech": row.get("part_of_speech"),
                "collocations": [c["phrase"] for c in collocations],
                "collocationsJa": [c["phrase_ja"] for c in collocations],
                "exampleEn": example_en,
                "exampleJa": example_ja,
                "soundPath": str(merged),
                "durationSeconds": round(total_duration, 3),
                "captionsEn": captions_en,
                "captionsJa": captions_ja,
            }
        )

    return slides
