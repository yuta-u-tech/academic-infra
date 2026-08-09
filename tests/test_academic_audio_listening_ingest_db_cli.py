from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "scripts" / "academic_audio_cli.py"

RESULT = {
    "format": "toeic-part2",
    "title": "テスト",
    "source_id": "logic.ch01.s01",
    "source_commit": "test-commit",
    "items": [
        {
            "item_id": "item-001",
            "parts": [
                {"role": "question", "text": "When will you finish checking the truth table?"},
                {"role": "choice", "text": "By the end of this afternoon."},
                {"role": "choice", "text": "In the small lecture room."},
                {"role": "choice", "text": "The table was quite accurate."},
            ],
            "answer_index": 0,
            "explanation": "正解は (A)。When で時期を聞いている。",
            "reason": "テスト用。",
        }
    ],
}


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(CLI), *args], cwd=ROOT, capture_output=True, text=True)


def test_listening_ingest_db_writes_review_id_and_is_idempotent(tmp_path: Path):
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps(RESULT, ensure_ascii=False), encoding="utf-8")
    db_path = tmp_path / "english.db"

    first = run_cli(
        "listening", "ingest-db",
        "--file", str(result_path), "--format", "toeic-part2",
        "--set-id", "20260810", "--db", str(db_path),
    )
    assert first.returncode == 0, first.stderr
    payload = json.loads(first.stdout)
    assert payload == {"set_id": "20260810", "part": "part2", "imported": 1}

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    row = connection.execute("SELECT review_id FROM generated_item WHERE kind = 'listening'").fetchone()
    connection.close()
    assert row["review_id"] == "toeic.listening.part2.20260810.0001"

    second = run_cli(
        "listening", "ingest-db",
        "--file", str(result_path), "--format", "toeic-part2",
        "--set-id", "20260810", "--db", str(db_path),
    )
    assert json.loads(second.stdout)["imported"] == 0
