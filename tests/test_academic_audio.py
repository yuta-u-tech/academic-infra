from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from academic_audio.planner import create_dialogue
from academic_audio.source import resolve_source

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "scripts" / "academic_audio_cli.py"
FIXTURE_COURSE = ROOT / "tests" / "fixtures" / "audio_course"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_resolves_review_manifest_section() -> None:
    source = resolve_source(review_id="logic.ch01.s01", repo_root=FIXTURE_COURSE)

    assert source.title == "真理値表"
    assert source.section_file == "sections/ch01-01.md"
    assert "命題は真または偽" in source.body


def test_creates_dialogue_segments() -> None:
    source = resolve_source(review_id="logic.ch01.s01", repo_root=FIXTURE_COURSE)
    script = create_dialogue(source, speed=0.9)

    assert script.source_id == "logic.ch01.s01"
    assert len(script.segments) >= 3
    assert script.segments[0].speaker == "host"
    assert all(segment.speed == 0.9 for segment in script.segments)


def test_cli_generate_wav_job_and_status(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    result = run_cli(
        "--state-dir",
        str(state_dir),
        "generate",
        "--review-id",
        "logic.ch01.s01",
        "--repo-root",
        str(FIXTURE_COURSE),
        "--engine",
        "wav",
        "--job-id",
        "fixture-job",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "completed"
    assert Path(payload["output_path"]).exists()
    assert (state_dir / "jobs" / "fixture-job" / "dialogue.json").exists()

    status = run_cli("--state-dir", str(state_dir), "job", "status", "fixture-job")
    assert status.returncode == 0
    assert json.loads(status.stdout)["rendered_segments"]


def test_cli_listening_generates_multiple_speeds(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    result = run_cli(
        "--state-dir",
        str(state_dir),
        "listening",
        "generate",
        "--review-id",
        "logic.ch01.s01",
        "--repo-root",
        str(FIXTURE_COURSE),
        "--engine",
        "wav",
        "--speeds",
        "0.8,1.2",
        "--listening-mode",
        "shadowing",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert len(payload["jobs"]) == 2
    assert {job["speed"] for job in payload["jobs"]} == {0.8, 1.2}
