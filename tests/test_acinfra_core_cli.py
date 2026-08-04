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


def test_competency_register_then_list(tmp_path: Path):
    db_path = tmp_path / "core.db"
    english_db_path = tmp_path / "english.db"
    run_cli(db_path, "goal", "create", "--id", "toeic-900", "--title", "TOEIC 900点")

    registered = run_cli(
        db_path, "competency", "register", "--goal", "toeic-900", "--domain", "toeic",
        "--english-db", str(english_db_path),
    )
    assert registered.returncode == 0, registered.stderr
    assert len(json.loads(registered.stdout)) == 3

    listed = run_cli(db_path, "competency", "list", "--goal", "toeic-900")
    assert listed.returncode == 0, listed.stderr
    assert {c["competency_id"] for c in json.loads(listed.stdout)} == {
        "toeic.vocabulary.recall",
        "toeic.part5.grammar",
        "toeic.part7.reading",
    }


def test_competency_mastery_reports_no_attempts_honestly(tmp_path: Path):
    db_path = tmp_path / "core.db"
    english_db_path = tmp_path / "english.db"
    run_cli(db_path, "goal", "create", "--id", "toeic-900", "--title", "TOEIC 900点")
    run_cli(
        db_path, "competency", "register", "--goal", "toeic-900", "--domain", "toeic",
        "--english-db", str(english_db_path),
    )

    mastery = run_cli(
        db_path, "competency", "mastery", "--goal", "toeic-900", "--english-db", str(english_db_path)
    )
    assert mastery.returncode == 0, mastery.stderr
    report = {entry["competency_id"]: entry for entry in json.loads(mastery.stdout)}
    assert report["toeic.vocabulary.recall"]["mastery"] is None
    assert report["toeic.part5.grammar"]["resource_gap_hint"]["gap_kind"] == "coverage"


def test_competency_mastery_can_open_requirements(tmp_path: Path):
    db_path = tmp_path / "core.db"
    english_db_path = tmp_path / "english.db"
    run_cli(db_path, "goal", "create", "--id", "toeic-900", "--title", "TOEIC 900点")
    run_cli(
        db_path, "competency", "register", "--goal", "toeic-900", "--domain", "toeic",
        "--english-db", str(english_db_path),
    )

    mastery = run_cli(
        db_path, "competency", "mastery", "--goal", "toeic-900",
        "--english-db", str(english_db_path), "--open-requirements",
    )
    assert mastery.returncode == 0, mastery.stderr

    requirements = run_cli(db_path, "requirement", "list", "--goal", "toeic-900")
    assert requirements.returncode == 0, requirements.stderr
    listed = json.loads(requirements.stdout)
    assert {r["requirement_id"] for r in listed} == {
        "auto.toeic.vocabulary.recall",
        "auto.toeic.part5.grammar",
        "auto.toeic.part7.reading",
    }
    assert all(r["status"] == "unresolved" for r in listed)


def test_resource_register_list_and_update_status(tmp_path: Path):
    db_path = tmp_path / "core.db"
    run_cli(db_path, "goal", "create", "--id", "toeic-900", "--title", "TOEIC 900点")

    registered = run_cli(
        db_path, "resource", "register", "--goal", "toeic-900", "--id", "vol8",
        "--title", "TOEIC公式問題集8", "--kind", "book",
    )
    assert registered.returncode == 0, registered.stderr
    assert json.loads(registered.stdout)["status"] == "candidate"

    run_cli(db_path, "resource", "update-status", "vol8", "active")

    listed = run_cli(db_path, "resource", "list", "--goal", "toeic-900", "--status", "active")
    assert [r["resource_id"] for r in json.loads(listed.stdout)] == ["vol8"]


def test_requirement_resolve_and_dismiss(tmp_path: Path):
    db_path = tmp_path / "core.db"
    english_db_path = tmp_path / "english.db"
    run_cli(db_path, "goal", "create", "--id", "toeic-900", "--title", "TOEIC 900点")
    run_cli(
        db_path, "competency", "register", "--goal", "toeic-900", "--domain", "toeic",
        "--english-db", str(english_db_path),
    )
    run_cli(
        db_path, "competency", "mastery", "--goal", "toeic-900",
        "--english-db", str(english_db_path), "--open-requirements",
    )

    resolved = run_cli(db_path, "requirement", "resolve", "auto.toeic.vocabulary.recall")
    assert resolved.returncode == 0, resolved.stderr
    assert json.loads(resolved.stdout)["status"] == "resolved"

    dismissed = run_cli(db_path, "requirement", "dismiss", "auto.toeic.part5.grammar")
    assert dismissed.returncode == 0, dismissed.stderr
    assert json.loads(dismissed.stdout)["status"] == "dismissed"
