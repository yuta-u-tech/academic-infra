from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "scripts" / "toeic_reading_cli.py"

ITEMS_JSON = {
    "title": "TOEIC Part 5",
    "items": [
        {
            "sentence": "The manager ____ the report yesterday.",
            "choices": ["submit", "submits", "submitted", "submitting"],
            "answer_index": 2,
            "explanation": "過去の出来事なので過去形。",
            "point": "時制",
        }
    ],
}


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(CLI), *args], cwd=ROOT, capture_output=True, text=True)


def test_ingest_writes_into_the_english_db(tmp_path: Path):
    items_path = tmp_path / "items.json"
    items_path.write_text(json.dumps(ITEMS_JSON, ensure_ascii=False), encoding="utf-8")
    db_path = tmp_path / "english.db"

    result = run_cli("ingest", "--items", str(items_path), "--set-id", "20260804", "--db", str(db_path))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"set_id": "20260804", "count": 1, "imported": 1}

    second = run_cli("ingest", "--items", str(items_path), "--set-id", "20260804", "--db", str(db_path))
    assert json.loads(second.stdout)["imported"] == 0
