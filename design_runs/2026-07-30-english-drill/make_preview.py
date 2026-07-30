#!/usr/bin/env python3
"""web/index.html に固定データを差し込んだ静的プレビューを作る。

批評のために画面を実際に見る必要があるが、生きたサーバー相手に headless Chrome を
走らせると読み込み待ちで止まる。fetch を差し替えて file:// で開ける形にしておくと、
1画面ずつ確実に撮れる。

usage: python3 make_preview.py            # 全画面ぶん出力
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent.parent / "web" / "index.html"

VOCAB = {
    "item_id": 1, "kind": "vocab", "review_id": "toeic.words1-400.0003", "course_id": "english",
    "difficulty": 3, "domain": "vocabulary", "sub_skill": "recall",
    "payload": {
        "kind": "vocab", "domain": "vocabulary", "sub_skill": "recall",
        "meaning": "（会議・式などを）主宰する、取り仕切る",
        "part_of_speech": "verb",
        "answer_pattern": "······· ····",
    },
}
GRAMMAR = {
    "item_id": 2, "kind": "grammar", "review_id": "voa.3714877", "course_id": "english",
    "difficulty": 4, "domain": "grammar", "sub_skill": "knowledge",
    "payload": {
        "kind": "grammar", "domain": "grammar", "sub_skill": "knowledge",
        "point": "前置詞 vs 接続詞（譲歩）",
        "sentence": "____ his reluctance to take public office, Washington accepted "
                    "the presidency as a duty.",
        "choices": ["Despite", "Although", "Even though", "However"],
    },
}
READING = {
    "item_id": 3, "kind": "reading", "review_id": "voa.3714877", "course_id": "english",
    "difficulty": 3, "domain": "reading", "sub_skill": "comprehension",
    "payload": {
        "kind": "reading", "domain": "reading", "sub_skill": "comprehension",
        "passage": "George Washington was the first president of the United States, but the "
                   "presidency was not what he wanted. He owned thousands of hectares of land "
                   "in Virginia, he had led the American colonists to freedom from British "
                   "rule as a general, and he had presided over the convention that created "
                   "the Constitution. For Washington, that was enough; he said he wanted to "
                   "retire from public service and return home. The country's new electors, "
                   "however, had other ideas.",
        "question": "Why did Washington become president?",
        "choices": [
            "He accepted it as a duty, although he had wanted to retire.",
            "He had campaigned for the office since the end of the war.",
            "The Constitution required the convention's chairman to serve.",
            "He needed the position to protect his land in Virginia.",
        ],
    },
}

ANSWER = {
    "attempt_id": 11, "correct": False, "error_cause": "knowledge_gap",
    "next_action": "review_drill", "mastery": 0.18, "next_review": "2026-07-31T00:00:00+00:00",
    "interval_days": 1, "revision_candidate_id": None,
    "explanation": "空所の後は his reluctance という名詞句なので前置詞が要る。"
                   "Although と Even though は接続詞で、後ろに主語＋動詞が必要。"
                   "However は副詞で名詞句を導けない。",
    "answer": "Despite",
    "example": None, "collocations": None,
}

SCENES = {
    "01-setup": {"queue": [GRAMMAR], "auto": []},
    "02-grammar": {"queue": [GRAMMAR, READING], "auto": ["start"]},
    "03-vocab": {"queue": [VOCAB, GRAMMAR], "auto": ["start", "type:preside"]},
    "04-reading": {"queue": [READING, GRAMMAR], "auto": ["start"]},
    "05-verdict": {"queue": [GRAMMAR, READING], "auto": ["start", "choose:1", "submit"]},
}

STUB = """
<script>
const FIXTURE = %(fixture)s;
window.fetch = async (url, options) => {
  const path = String(url);
  const body = (data) => ({ ok: true, status: 200, json: async () => data, text: async () => "" });
  if (path.startsWith("/api/courses"))
    return body({ courses: [{ course_id: "english", course_name: "英語（一般・TOEIC）" }] });
  if (path.startsWith("/api/sessions")) return body({ session_id: 7 });
  if (path.startsWith("/api/queue")) return body({ items: FIXTURE.queue });
  if (path.startsWith("/api/hint")) return body({ hint: "p······ o···" });
  if (path.startsWith("/api/answer")) return body(FIXTURE.answer);
  if (path.startsWith("/api/grade")) return body({ interval_days: 1 });
  return body({});
};
window.__scene = FIXTURE;
</script>
"""

DRIVER = """
<script>
// 目的の画面まで進める。描画は同期なので、待ちは1フレームで足りる。
const frame = () => new Promise((r) => setTimeout(r, 120));
const press = (key) => document.dispatchEvent(new KeyboardEvent("keydown",
  { key, bubbles: true, cancelable: true }));
(async () => {
  await frame(); await frame();
  for (const step of window.__scene.auto) {
    await frame(); await frame();
    if (step === "start") document.getElementById("start")?.click();
    else if (step.startsWith("choose:")) press(step.split(":")[1]);
    else if (step === "submit") press("Enter");
    else if (step.startsWith("type:")) for (const c of step.split(":")[1]) press(c);
  }
  await frame();
  document.documentElement.setAttribute("data-ready", "1");
})();
</script>
"""


def build(name: str, scene: dict) -> Path:
    html = SOURCE.read_text(encoding="utf-8")
    fixture = json.dumps({**scene, "answer": ANSWER}, ensure_ascii=False)
    html = html.replace("<script>\n\"use strict\";", STUB % {"fixture": fixture} + '<script>\n"use strict";', 1)
    html = html.replace("</body>", DRIVER + "</body>", 1)
    path = HERE / f"{name}.preview.html"
    path.write_text(html, encoding="utf-8")
    return path


def main() -> None:
    for name, scene in SCENES.items():
        print(build(name, scene))


if __name__ == "__main__":
    main()
