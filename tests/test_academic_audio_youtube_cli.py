from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "scripts" / "academic_audio_cli.py"
FIXTURE_COURSE = ROOT / "tests" / "fixtures" / "audio_course"

try:
    import PIL  # noqa: F401

    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or not _HAS_PIL, reason="ffmpeg または Pillow が無い"
)


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(CLI), *args], cwd=ROOT, capture_output=True, text=True)


@pytest.fixture
def rendered_job(tmp_path: Path) -> tuple[Path, str]:
    """A real wav-engine job with a real artifact.json (generate をそのまま使う)。"""
    state_dir = tmp_path / "state"
    result = run_cli(
        "--state-dir", str(state_dir), "generate",
        "--review-id", "logic.ch01.s01", "--repo-root", str(FIXTURE_COURSE),
        "--engine", "wav", "--job-id", "yt-job",
    )
    assert result.returncode == 0, result.stderr
    return state_dir, "yt-job"


def test_youtube_doctor_local_needs_no_credentials(tmp_path: Path) -> None:
    result = run_cli("--state-dir", str(tmp_path / "state"), "youtube", "doctor", "--local")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ok"] is True


def test_youtube_publish_dry_run_previews_metadata(rendered_job: tuple[Path, str]) -> None:
    state_dir, job_id = rendered_job

    result = run_cli("--state-dir", str(state_dir), "youtube", "publish", job_id, "--dry-run", "--local")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "dry_run"
    assert payload["preview"]["title"]
    # dry-run では動画を作らない。
    assert not (state_dir / "jobs" / job_id / "video").exists()


def test_youtube_publish_local_builds_a_real_video_and_dedups(rendered_job: tuple[Path, str]) -> None:
    state_dir, job_id = rendered_job

    first = run_cli("--state-dir", str(state_dir), "youtube", "publish", job_id, "--local")
    assert first.returncode == 0, first.stderr
    first_payload = json.loads(first.stdout)
    assert first_payload["status"] == "uploaded"
    assert Path(first_payload["url"]).exists()

    second = run_cli("--state-dir", str(state_dir), "youtube", "publish", job_id, "--local")
    assert second.returncode == 0, second.stderr
    assert json.loads(second.stdout)["status"] == "duplicate"


def test_youtube_status_reports_after_publish(rendered_job: tuple[Path, str]) -> None:
    state_dir, job_id = rendered_job
    run_cli("--state-dir", str(state_dir), "youtube", "publish", job_id, "--local")

    result = run_cli("--state-dir", str(state_dir), "youtube", "status", job_id)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "uploaded"


def test_youtube_status_for_an_unknown_publication_fails_clearly(tmp_path: Path) -> None:
    result = run_cli("--state-dir", str(tmp_path / "state"), "youtube", "status", "never-existed")

    assert result.returncode == 1
    assert result.stderr.strip()


def test_youtube_publish_without_an_artifact_fails_clearly(tmp_path: Path) -> None:
    result = run_cli("--state-dir", str(tmp_path / "state"), "youtube", "publish", "no-such-job", "--local")

    assert result.returncode == 1
    assert "artifact.json" in result.stderr


def test_youtube_publish_without_local_needs_credentials(rendered_job: tuple[Path, str], monkeypatch) -> None:
    state_dir, job_id = rendered_job
    # ローカルの資格情報ファイルが実際にあるとテスト結果が環境依存になるため、
    # 環境変数もローカルファイルも見えない状態を作って確認する。
    result = subprocess.run(
        [sys.executable, str(CLI), "--state-dir", str(state_dir), "youtube", "publish", job_id],
        cwd=ROOT, capture_output=True, text=True,
        env={"HOME": str(state_dir / "fake-home")},
    )

    assert result.returncode == 1
    assert "YouTube 認証情報が不足しています" in result.stderr
