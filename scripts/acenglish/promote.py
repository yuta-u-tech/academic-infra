"""追記候補 → findings.json。既存の Issue 昇華経路へ合流させる。

新しい承認 UI も新しい Issue 作成コードも作らない。`promote_drive_comments.py` が
既に「findings.json を読み、`--pick` で選ばれたものだけを Issue 化する」を担っているので、
ここはその入力を作るところで止める。`comment_id` / `file_id` は Drive 由来ではないので
持たせない（あの実装は無ければ Drive 返信を黙って飛ばす）。

    python3 scripts/acenglish_cli.py findings --course dsa --out /tmp/findings.json
    python3 scripts/promote_drive_comments.py --course dsa --findings /tmp/findings.json \
        --pick 1 --no-drive-reply
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .db import now_iso


def open_candidates(connection: sqlite3.Connection, course_id: str | None = None) -> list[dict]:
    """Issue 化すべき候補だけを返す。

    外部素材（TOEIC/VOA/TED）由来の候補は `target_kind = 'english_note'` で、直すべき
    科目資料が無い。ここに混ぜると科目リポジトリへ無関係な Issue が立つので除く
    （そちらは `notes.write_drafts()` が扱う）。
    """
    if course_id:
        rows = connection.execute(
            "SELECT * FROM revision_candidate WHERE status = 'open'"
            " AND target_kind = 'course_repo' AND course_id = ? ORDER BY id",
            (course_id,),
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT * FROM revision_candidate WHERE status = 'open'"
            " AND target_kind = 'course_repo' ORDER BY id"
        ).fetchall()
    return [dict(row) for row in rows]


def build_findings(candidates: list[dict]) -> dict:
    """`templates/review-issue.md` 形式へ。index は 1 始まり（`--pick` がこれを指す）。"""
    findings = []
    for index, candidate in enumerate(candidates, start=1):
        evidence = json.loads(candidate["evidence"])
        findings.append(
            {
                "index": index,
                "candidate_id": candidate["id"],
                "review_id": candidate["review_id"],
                "title": candidate["title"],
                "source_file": candidate["source_file"],
                "problem": candidate["problem"],
                "fix_spec": json.loads(candidate["fix_spec"]),
                "quote": evidence.get("item_prompt", ""),
                "evidence": evidence,
            }
        )
    return {"source": "english-learning", "generated_at": now_iso(), "findings": findings}


def export_findings(
    connection: sqlite3.Connection, destination: Path, course_id: str | None = None
) -> tuple[Path, list[int]]:
    candidates = open_candidates(connection, course_id)
    document = build_findings(candidates)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return destination, [c["id"] for c in candidates]


def mark_promoted(connection: sqlite3.Connection, candidate_ids: list[int]) -> int:
    """Issue 化が済んだものを閉じる。

    export だけでは閉じない。Issue を実際に作ったかどうかは
    `promote_drive_comments.py` の `--pick` の結果次第で、export 時点では分からないため。
    """
    if not candidate_ids:
        return 0
    placeholders = ",".join("?" for _ in candidate_ids)
    cursor = connection.execute(
        f"UPDATE revision_candidate SET status = 'promoted', promoted_at = ? "
        f"WHERE id IN ({placeholders}) AND status = 'open'",
        (now_iso(), *candidate_ids),
    )
    connection.commit()
    return cursor.rowcount
