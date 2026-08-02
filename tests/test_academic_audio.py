from __future__ import annotations

import json
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import pytest

from academic_audio.engines import PiperEngine, TTSEngineError, select_engine
from academic_audio.models import DialogueScript, DialogueSegment
from academic_audio.planner import create_dialogue
from academic_audio.pronunciation import normalize
from academic_audio.source import resolve_source
from style_bert_vits2_tts import DEFAULT_VOICE_MAP, StyleBertVITS2Error, parse_voice_map

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


def _write_voice_model(tmp_path: Path, family: str) -> str:
    model = tmp_path / f"{family}-voice.onnx"
    model.write_bytes(b"")
    model.with_suffix(".onnx.json").write_text(
        json.dumps({"language": {"family": family, "code": family}}), encoding="utf-8"
    )
    return str(model)


def test_piper_requires_a_voice_model() -> None:
    available, reason = PiperEngine().available()

    if available:
        pytest.fail(f"expected the model-less default invocation to be unavailable: {reason}")
    assert "piper" in reason


def test_piper_reports_ready_with_a_voice_model(tmp_path: Path) -> None:
    engine = PiperEngine(model=_write_voice_model(tmp_path, "en"))

    if shutil.which("piper") is None:
        pytest.skip("piper is not installed")
    assert engine.available()[0]


def test_piper_rejects_a_language_mismatch(tmp_path: Path) -> None:
    engine = PiperEngine(model=_write_voice_model(tmp_path, "en"))
    segment = DialogueSegment(id="seg-001", speaker="host", text="命題は真または偽", language="ja")

    with pytest.raises(TTSEngineError, match="language"):
        engine.render(segment, tmp_path / "out.wav")


def test_quality_mode_fails_loudly_without_style_bert() -> None:
    with pytest.raises(TTSEngineError):
        select_engine("auto", "quality")


def test_normalize_drops_markdown_markers() -> None:
    assert normalize("確認したいです。 - 命題は真または偽の値を取る。") == "確認したいです。 命題は真または偽の値を取る。"
    assert normalize("## 真理値表") == "真理値表"
    assert normalize("AND-OR 変換") == "AND-OR 変換"


def test_style_bert_voice_map_defaults_and_overrides() -> None:
    assert parse_voice_map(None) == DEFAULT_VOICE_MAP
    assert parse_voice_map("learner=jvnv-F2-jp")["learner"] == "jvnv-F2-jp"
    assert parse_voice_map("learner=jvnv-F2-jp")["host"] == DEFAULT_VOICE_MAP["host"]

    with pytest.raises(StyleBertVITS2Error):
        parse_voice_map("broken")


def _authored_script(**overrides: object) -> dict:
    """A dialogue.json as audio/prompts/dialogue.md tells the author to write it."""
    segment = {
        "id": "seg-001",
        "speaker": "host",
        "text": "今日は真理値表を扱います。",
        "language": "ja",
        "emotion": "Neutral",
        "speed": 1.0,
        "pause": 0.4,
        "source_section": "logic.ch01.s01",
    }
    segment.update(overrides)
    return {
        "title": "真理値表",
        "source_id": "logic.ch01.s01",
        "source_commit": "test-commit",
        "segments": [segment],
    }


def test_authored_script_round_trips() -> None:
    script = DialogueScript.from_json_dict(_authored_script())

    assert script.segments[0].emotion == "Neutral"
    assert script.segments[0].pause == 0.4


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda data: data.update(segments=[]), "segments が空"),
        (lambda data: data.pop("title"), "title がありません"),
        (lambda data: data["segments"][0].update(style="Happy"), "未知のフィールド"),
        (lambda data: data["segments"][0].pop("text"), "text がありません"),
        (lambda data: data["segments"].append(data["segments"][0]), "重複"),
    ],
)
def test_broken_authored_script_reports_where(mutate, expected: str) -> None:
    data = _authored_script()
    mutate(data)

    with pytest.raises(ValueError, match=expected):
        DialogueScript.from_json_dict(data)


def test_cli_render_takes_an_authored_script(tmp_path: Path) -> None:
    script_path = tmp_path / "dialogue.json"
    script_path.write_text(json.dumps(_authored_script(), ensure_ascii=False), encoding="utf-8")
    state_dir = tmp_path / "state"

    result = run_cli(
        "--state-dir",
        str(state_dir),
        "render",
        "--script",
        str(script_path),
        "--engine",
        "wav",
        "--job-id",
        "authored",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "completed"
    assert Path(payload["output_path"]).exists()
    # 台本がジョブ配下に写っていないと job resume が読めない。
    assert (state_dir / "jobs" / "authored" / "dialogue.json").exists()
    assert (state_dir / "jobs" / "authored" / "dialogue.md").exists()


def test_render_inserts_the_authored_pause(tmp_path: Path) -> None:
    data = _authored_script(pause=1.0)
    data["segments"].append({**data["segments"][0], "id": "seg-002", "pause": 0.0})
    script_path = tmp_path / "dialogue.json"
    script_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    state_dir = tmp_path / "state"

    result = run_cli(
        "--state-dir", str(state_dir), "render", "--script", str(script_path),
        "--engine", "wav", "--job-id", "paused",
    )
    assert result.returncode == 0, result.stderr

    job_dir = state_dir / "jobs" / "paused"
    segments = _wav_seconds(job_dir / "segments" / "seg-001.wav") + _wav_seconds(job_dir / "segments" / "seg-002.wav")
    # seg-001 の後ろにだけ 1.0 秒の無音が入る。
    assert _wav_seconds(job_dir / "output.wav") == pytest.approx(segments + 1.0, abs=0.01)


def _wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / handle.getframerate()


def test_cli_render_rejects_a_broken_script(tmp_path: Path) -> None:
    data = _authored_script()
    data["segments"][0]["style"] = "Happy"
    script_path = tmp_path / "dialogue.json"
    script_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    result = run_cli("--state-dir", str(tmp_path / "state"), "render", "--script", str(script_path), "--engine", "wav")

    assert result.returncode == 1
    assert "未知のフィールド" in result.stderr


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
