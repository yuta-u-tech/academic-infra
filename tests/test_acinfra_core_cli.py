from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "scripts" / "acinfra_core_cli.py"


def run_cli(db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), "--db", str(db_path), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_goal_create_then_show(tmp_path: Path):
    db_path = tmp_path / "core.db"

    created = run_cli(db_path, "goal", "create", "--id", "toeic-900", "--title", "TOEIC 900点")
    assert created.returncode == 0, created.stderr
    assert json.loads(created.stdout)["goal_id"] == "toeic-900"

    shown = run_cli(db_path, "goal", "show", "toeic-900")
    assert shown.returncode == 0, shown.stderr
    assert json.loads(shown.stdout)["title"] == "TOEIC 900点"


def test_goal_create_duplicate_fails(tmp_path: Path):
    db_path = tmp_path / "core.db"
    run_cli(db_path, "goal", "create", "--id", "toeic-900", "--title", "TOEIC 900点")

    duplicate = run_cli(db_path, "goal", "create", "--id", "toeic-900", "--title", "重複")
    assert duplicate.returncode == 1
    assert "toeic-900" in duplicate.stderr


def test_goal_list_and_update_status(tmp_path: Path):
    db_path = tmp_path / "core.db"
    run_cli(db_path, "goal", "create", "--id", "a", "--title", "A")
    run_cli(db_path, "goal", "create", "--id", "b", "--title", "B")

    run_cli(db_path, "goal", "update-status", "b", "paused")

    active = run_cli(db_path, "goal", "list", "--status", "active")
    assert [g["goal_id"] for g in json.loads(active.stdout)] == ["a"]
