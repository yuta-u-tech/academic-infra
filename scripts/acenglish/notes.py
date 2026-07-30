"""外部素材の誤答 → `~/english-notes` の追記候補。

科目資料の還元先は GitHub Issue（既存の `promote_drive_comments.py`）だが、TOEIC 語彙や
VOA の記事には「直すべき章」も「Codex に投げる仕様」も無い。相手は自分のノートなので、
Issue を挟まずに Markdown の下書きを置く方が素直で速い。

**`notes/` には書かない。`drafts/` までで止める。** 既存のノートを無断で書き換えない、
という原則は科目資料と同じで、確認して初めて自分の言葉で `notes/` へ反映する。
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from .db import now_iso

DEFAULT_NOTES_ENV = "ENGLISH_NOTES_HOME"
_DEFAULT_NOTES_HOME = Path.home() / "english-notes"
DRAFTS_DIR = "drafts"


class NotesRepositoryError(Exception):
    pass


def notes_home() -> Path:
    override = os.environ.get(DEFAULT_NOTES_ENV, "").strip()
    return Path(override) if override else _DEFAULT_NOTES_HOME


def open_note_candidates(connection: sqlite3.Connection) -> list[dict]:
    rows = connection.execute(
        "SELECT * FROM revision_candidate WHERE status = 'open' AND target_kind = 'english_note'"
        " ORDER BY id"
    ).fetchall()
    return [dict(row) for row in rows]


def render_draft(candidate: dict) -> str:
    """1件の追記候補を Markdown の下書きにする。

    ここで書けるのは「何を、なぜ書き足すべきか」まで。本文（間違えた理由・自作の例文）は
    人が埋める前提で空欄にしておく。埋まっていない下書きが `notes/` に紛れ込まないよう、
    チェックボックスを残す。
    """
    evidence = json.loads(candidate["evidence"])
    fix_spec = json.loads(candidate["fix_spec"])
    origin = evidence.get("origin") or evidence.get("source", "不明")

    steps = "\n".join(f"{i}. {step}" for i, step in enumerate(fix_spec, start=1))
    return f"""---
review_id: {candidate["review_id"]}
source: {evidence.get("source", "unknown")}
origin: {origin}
domain: {evidence.get("domain", "")}
sub_skill: {evidence.get("sub_skill", "")}
target_note: {candidate["source_file"]}
created_at: {candidate["created_at"]}
status: draft
---

# {candidate["title"]}

## 何が起きたか

{candidate["problem"]}

| 指標 | 値 |
|---|---|
| 連続誤答 | {evidence.get("error_streak", "-")} 回 |
| 習熟度 | {evidence.get("mastery", "-")} |
| 回答時間の中央値 | {evidence.get("latency_ms_p50", "-")} ms |
| 出題内容 | {evidence.get("item_prompt", "-")} |

## 書き足すこと

{steps}

## 自分の言葉で（ここを埋める）

- 何と取り違えた？
-
- 区別のしかた:
-
- 自作の例文:
-

## 反映

- [ ] 上を埋めた
- [ ] `{candidate["source_file"]}` へ反映した
- [ ] このファイルを削除した
"""


def draft_filename(candidate: dict) -> str:
    created = candidate["created_at"][:10]
    safe_id = candidate["review_id"].replace("/", "-")
    return f"{created}-{safe_id}.md"


def write_drafts(
    connection: sqlite3.Connection, home: Path | None = None, mark: bool = False
) -> list[Path]:
    """open な英語ノート候補を drafts/ へ書き出す。

    `mark=True` のときだけ候補を閉じる。書き出しただけでは閉じないのは科目資料側と同じで、
    実際にノートへ反映したかどうかは、この時点では分からないため。
    """
    root = home or notes_home()
    if not (root / ".git").exists():
        raise NotesRepositoryError(
            f"{root} が english-notes リポジトリではありません。"
            f"別の場所を使うなら {DEFAULT_NOTES_ENV} を設定してください。"
        )

    drafts = root / DRAFTS_DIR
    drafts.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    candidates = open_note_candidates(connection)
    for candidate in candidates:
        path = drafts / draft_filename(candidate)
        path.write_text(render_draft(candidate), encoding="utf-8")
        written.append(path)

    if mark and candidates:
        placeholders = ",".join("?" for _ in candidates)
        connection.execute(
            f"UPDATE revision_candidate SET status = 'promoted', promoted_at = ? "
            f"WHERE id IN ({placeholders})",
            (now_iso(), *[c["id"] for c in candidates]),
        )
        connection.commit()
    return written


def summarize(written: list[Path]) -> str:
    if not written:
        return "英語ノートへの追記候補はありません。"
    today = datetime.now().strftime("%Y-%m-%d")
    names = "\n".join(f"  - {path.name}" for path in written)
    return f"{today}: {len(written)} 件の下書きを書きました。\n{names}"
