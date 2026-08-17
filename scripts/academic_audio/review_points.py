"""復習動画のAnswerPoint/ExplanationPointで使う、崩れないラベル体系。

自由記述のlabelをClaudeに書かせていたところ、実際に「正解の理由」「headlineとの
違い」のような長文がlabelに入り、丸バッジ内で折り返されて動画が崩れる事故が
起きた(2026-08-18)。バッジの表示テキストは有限個の種類(kind)からコード側が
決め、Claudeは`kind`(下記の固定値のいずれか)と`text`(自由記述。バッジ崩れとは
無関係な本文側)だけを書く。
"""

from __future__ import annotations

POINT_KIND_LABELS: dict[str, str] = {
    "reason": "理由",
    "distractor": "誤答",
    "grammar": "文法",
    "collocation": "語法",
    "vocab": "語彙",
    "note": "注意",
}


class UnknownPointKindError(ValueError):
    pass


def labelled_points(points: list[dict]) -> list[dict]:
    """`points`: `[{"kind": <POINT_KIND_LABELSのキー>, "text": str}, ...]` を、
    TSX側が期待する `[{"label": str, "text": str}]` へ変換する。

    同じkindが2回以上出たら「誤答1」「誤答2」のように連番を振る(同じ文言の
    バッジが並んでも区別できるように)。1回しか出ないkindには数字を付けない。
    """
    totals: dict[str, int] = {}
    for point in points:
        totals[point["kind"]] = totals.get(point["kind"], 0) + 1

    counts: dict[str, int] = {}
    result = []
    for point in points:
        kind = point["kind"]
        if kind not in POINT_KIND_LABELS:
            raise UnknownPointKindError(
                f"未知のpoint kind: {kind!r}（使えるのは {', '.join(POINT_KIND_LABELS)}）"
            )
        counts[kind] = counts.get(kind, 0) + 1
        label = POINT_KIND_LABELS[kind]
        if totals[kind] > 1:
            label = f"{label}{counts[kind]}"
        result.append({"label": label, "text": point["text"]})
    return result
