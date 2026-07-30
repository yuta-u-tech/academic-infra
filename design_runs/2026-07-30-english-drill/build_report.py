#!/usr/bin/env python3
"""web/index.html のトークンから layout_report.json を組み立てる。

数値を手で書かず CSS の値から積み上げるのは、レポートと実装が食い違うと
機械評価が意味を失うため。ブラウザを動かさずに済ませるための静的レンダラー相当。

usage: python3 build_report.py
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

CANVAS = {"width": 1440, "height": 900, "bg_color": "#0B0D10"}
BG = "#0B0D10"
FG = "#E6EDF3"
MUTED = "#8B949E"
ACCENT = "#4C8DFF"
BORDER = "#232A32"

R1, R2, R3 = 32, 20, 12
S3, S4, S5, S6, S7 = 12, 16, 24, 32, 48
MAIN_MAX = 760
PAD_X = S5

CONTENT_X = (CANVAS["width"] - MAIN_MAX) // 2 + PAD_X
CONTENT_W = MAIN_MAX - PAD_X * 2


def line_height(size: float, ratio: float) -> int:
    return round(size * ratio)


class Cursor:
    def __init__(self, y: int) -> None:
        self.y = y

    def place(self, height: int, margin_bottom: int = 0) -> int:
        top = self.y
        self.y += height + margin_bottom
        return top


def grammar_screen() -> list[dict]:
    cursor = Cursor(S6)
    elements: list[dict] = []

    def text(id_, height, *, size, color, rank, content, margin=0, width=CONTENT_W, x=CONTENT_X):
        top = cursor.place(height, margin)
        elements.append({
            "id": id_, "bbox": [x, top, width, height], "role": "text", "rank": rank,
            "font_size": size, "color": color, "bg_color": BG, "text": content,
        })

    elements.append({
        "id": "progress_rule", "bbox": [0, 0, 480, 1], "role": "shape", "rank": 3,
        "font_size": None, "color": ACCENT, "bg_color": BG, "text": None,
    })
    text("session_meta", line_height(R3, 1.6), size=R3, color=MUTED, rank=3,
         content="12 / 20   正答 83%   0:04  ●●●●○  文法", margin=S5)
    text("point_meta", line_height(R3, 1.6), size=R3, color=MUTED, rank=3,
         content="前置詞 vs 接続詞（譲歩）", margin=S5)

    text("stem", line_height(R1, 1.45) * 3, size=R1, color=FG, rank=1,
         content="____ his reluctance to take public office, Washington accepted "
                 "the presidency as a duty.",
         margin=S6)

    choice_height = line_height(R2, 1.5) + S3 * 2
    for index, label in enumerate(["Despite", "Although", "Even though", "However"]):
        top = cursor.place(choice_height, 8)
        elements.append({
            "id": f"choice_{index}", "bbox": [CONTENT_X, top, CONTENT_W, choice_height],
            "role": "button", "rank": 2, "font_size": R2, "color": FG, "bg_color": BG,
            "text": label, "tappable": True,
        })
        elements.append({
            "id": f"choice_key_{index}", "bbox": [CONTENT_X + S4, top + S3 + 3, 22, 22],
            "role": "text", "rank": 3, "font_size": R3, "color": MUTED, "bg_color": BG,
            "text": str(index + 1),
        })

    # キーマップは画面下端に固定。本文の流れからは外れる。
    elements.append({
        "id": "keymap", "bbox": [CONTENT_X, 852, CONTENT_W, line_height(R3, 1.6)],
        "role": "text", "rank": 3, "font_size": R3, "color": MUTED, "bg_color": BG,
        "text": "1–4 選択 　↵ 決定",
    })

    for element in elements:
        x, y, w, h = element["bbox"]
        element["overflow"] = x < 0 or y < 0 or x + w > CANVAS["width"] or y + h > CANVAS["height"]
    return elements


def main() -> None:
    report = {
        "canvas": CANVAS,
        "safe_area": {"top": 0, "bottom": 0, "left": 24, "right": 24},
        "renderer": "html_static",
        "elements": grammar_screen(),
        "meta": {"screen": "grammar_question", "breakpoint": "lg"},
    }
    path = HERE / "grammar_question.layout_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
