from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "scripts" / "toeic_reading_cli.py"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(CLI), *args], cwd=ROOT, capture_output=True, text=True)


def _items_payload(count: int) -> dict:
    return {
        "title": "shuffle テスト",
        "items": [
            {
                "sentence": f"Sentence number {i} ____ here.",
                "choices": ["a", "b", "c", "d"],
                "answer_index": 0,
                "explanation": f"explanation {i}",
                "point": f"point {i}",
                "pattern": "A",
                "pattern_note": "note",
            }
            for i in range(count)
        ],
    }


def test_shuffle_keeps_all_items_but_changes_order(tmp_path: Path):
    items_path = tmp_path / "items.json"
    items_path.write_text(json.dumps(_items_payload(50)), encoding="utf-8")

    original_sentences = [item["sentence"] for item in _items_payload(50)["items"]]

    result = run_cli("shuffle", "--items", str(items_path))
    assert result.returncode == 0, result.stderr

    shuffled = json.loads(items_path.read_text(encoding="utf-8"))
    shuffled_sentences = [item["sentence"] for item in shuffled["items"]]

    assert sorted(shuffled_sentences) == sorted(original_sentences)
    assert shuffled_sentences != original_sentences  # 50件もあれば確率的にまず一致しない
    assert shuffled["title"] == "shuffle テスト"


def test_shuffle_writes_to_out_when_given(tmp_path: Path):
    items_path = tmp_path / "items.json"
    out_path = tmp_path / "shuffled.json"
    items_path.write_text(json.dumps(_items_payload(10)), encoding="utf-8")

    result = run_cli("shuffle", "--items", str(items_path), "--out", str(out_path))
    assert result.returncode == 0, result.stderr

    assert out_path.exists()
    original = json.loads(items_path.read_text(encoding="utf-8"))
    assert len(original["items"]) == 10  # --items 自体は変更されない


def test_shuffle_rejects_empty_items(tmp_path: Path):
    items_path = tmp_path / "items.json"
    items_path.write_text(json.dumps({"title": "empty", "items": []}), encoding="utf-8")

    result = run_cli("shuffle", "--items", str(items_path))
    assert result.returncode != 0
