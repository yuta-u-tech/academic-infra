from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from academic_audio.artifact import build_chapters, build_timeline
from academic_audio.formats import FormatError, ListeningFormat, available_formats, load_format
from academic_audio.items import ItemValidationError, load_result, to_answers, to_script
from academic_audio.models import DialogueScript, DialogueSegment
from academic_audio.worksheet import escape, render_tex

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "scripts" / "academic_audio_cli.py"
FIXTURE_COURSE = ROOT / "tests" / "fixtures" / "audio_course"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(CLI), *args], cwd=ROOT, capture_output=True, text=True)


def _result(**overrides) -> dict:
    item = {
        "item_id": "item-001",
        "parts": [
            {"role": "question", "text": "When will you finish checking the truth table?"},
            {"role": "choice", "text": "By the end of this afternoon."},
            {"role": "choice", "text": "In the small lecture room."},
            {"role": "choice", "text": "The table was quite accurate."},
        ],
        "answer_index": 0,
        "explanation": "正解は (A)。When で時期を聞いている。",
        "reason": "資料の真理値表の記述に対応する。",
    }
    item.update(overrides)
    return {
        "format": "toeic-part2",
        "title": "真理値表 リスニング",
        "source_id": "logic.ch01.s01",
        "source_commit": "test-commit",
        "items": [item],
    }


@pytest.fixture
def toeic() -> ListeningFormat:
    return load_format("toeic-part2")


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "result.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_toeic_part2_is_available() -> None:
    assert "toeic-part2" in available_formats()


def test_format_exposes_the_item_shape(toeic: ListeningFormat) -> None:
    assert toeic.language == "en"
    assert toeic.answer_in_audio is True  # 本番同様、応答は音声でのみ読まれる
    assert toeic.choice_count == 3
    assert toeic.segments_per_item == 4
    # 本文の作問方針も一緒に読めていること（front matter だけでは作問できない）。
    assert "誤答" in toeic.guidance


def test_unknown_format_lists_what_exists() -> None:
    with pytest.raises(FormatError, match="toeic-part2"):
        load_format("ielts-section1")


def test_valid_result_loads(tmp_path: Path, toeic: ListeningFormat) -> None:
    listening_set = load_result(_write(tmp_path, _result()), toeic)

    assert len(listening_set.items) == 1
    assert listening_set.items[0].answer_index == 0


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        # 選択肢が2つしかない
        ({"parts": [
            {"role": "question", "text": "When will you finish checking the truth table?"},
            {"role": "choice", "text": "By the end of this afternoon."},
            {"role": "choice", "text": "In the small lecture room."},
        ]}, "構成が形式と違います"),
        # 質問が長すぎる（6〜15語）
        ({"parts": [
            {"role": "question", "text": "When exactly will you be able to finish checking the whole truth table for us this afternoon"},
            {"role": "choice", "text": "By the end of this afternoon."},
            {"role": "choice", "text": "In the small lecture room."},
            {"role": "choice", "text": "The table was quite accurate."},
        ]}, "語です"),
        ({"answer_index": 5}, "範囲外"),
        ({"answer_index": None}, "answer_index がありません"),
        ({"explanation": ""}, "explanation がありません"),
    ],
)
def test_invalid_result_says_what_is_wrong(tmp_path: Path, toeic: ListeningFormat, overrides, expected: str) -> None:
    with pytest.raises(ItemValidationError, match=expected):
        load_result(_write(tmp_path, _result(**overrides)), toeic)


def test_items_become_segments_with_item_id_and_role(tmp_path: Path, toeic: ListeningFormat) -> None:
    script = to_script(load_result(_write(tmp_path, _result()), toeic), toeic)

    # "Number 1." は質問文と同じ発話にまとめる（別々に合成すると機械的な読み方になるため）。
    assert [segment.role for segment in script.segments] == ["question", "choice", "choice", "choice"]
    assert script.segments[0].text == "Number 1. When will you finish checking the truth table?"
    assert all(segment.item_id == "item-001" for segment in script.segments)
    assert all(segment.language == "en" for segment in script.segments)
    # 疑問文の後は「本当に尋ねている」間(1.2秒)、最後の選択肢だけ次の問題までのマーク時間(5秒)。
    assert script.segments[0].pause == 1.2
    choice_segments = [s for s in script.segments if s.role == "choice"]
    assert [s.pause for s in choice_segments] == [1.0, 1.0, 5.0]


def test_answers_carry_the_label_and_text(tmp_path: Path, toeic: ListeningFormat) -> None:
    answers = to_answers(load_result(_write(tmp_path, _result()), toeic))

    assert answers["items"][0]["answer_label"] == "A"
    assert answers["items"][0]["answer_text"] == "By the end of this afternoon."


def test_worksheet_prints_the_question_but_not_the_choices_on_the_question_page(
    tmp_path: Path, toeic: ListeningFormat
) -> None:
    tex = render_tex(load_result(_write(tmp_path, _result()), toeic), toeic)

    questions, _, answers = tex.partition(r"\section*{解答と解説}")
    # 質問文は印刷してよい（音声の冒頭で読まれるだけで、正解の手がかりにはならない）。
    # 復習用に、聴き取れなくても内容を確認できるようにする。
    assert "When will you finish checking" in questions
    assert "When will you finish checking" in answers
    # 本番同様、応答(A)(B)(C)は音声でのみ読まれる（answer_in_audio: true）。
    # 冊子の設問ページには印刷しない。答え合わせページにだけ出す。
    assert "By the end of this afternoon." not in questions
    assert "By the end of this afternoon." in answers


def test_latex_special_characters_are_escaped() -> None:
    assert escape("100% & <A_B>") == r"100\% \& <A\_B>"


def test_worksheet_includes_the_youtube_url_when_given(tmp_path: Path, toeic: ListeningFormat) -> None:
    tex = render_tex(load_result(_write(tmp_path, _result()), toeic), toeic, youtube_url="https://youtu.be/abc123")

    assert r"\url{https://youtu.be/abc123}" in tex


def test_worksheet_omits_the_youtube_line_when_no_url(tmp_path: Path, toeic: ListeningFormat) -> None:
    tex = render_tex(load_result(_write(tmp_path, _result()), toeic), toeic)

    assert r"\url{" not in tex


def test_timeline_accumulates_pause_and_groups_chapters() -> None:
    script = DialogueScript(
        title="t", source_id="s", source_commit="c",
        segments=[
            DialogueSegment(id="seg-001", speaker="narrator", text="a", pause=0.5, item_id="item-001", role="question"),
            DialogueSegment(id="seg-002", speaker="narrator", text="b", pause=0.5, item_id="item-001", role="choice"),
            DialogueSegment(id="seg-003", speaker="narrator", text="c", pause=0.5, item_id="item-002", role="question"),
        ],
    )

    timings = build_timeline(script, _FakeDir(1.0), ["seg-001", "seg-002", "seg-003"])
    assert [(t.start, t.end) for t in timings] == [(0.0, 1.0), (1.5, 2.5), (3.0, 4.0)]

    chapters = build_chapters(timings)
    assert [(c.item_id, c.start, c.end, c.title) for c in chapters] == [
        ("item-001", 0.0, 2.5, "第1問"),
        ("item-002", 3.0, 4.0, "第2問"),
    ]


class _FakeDir:
    """Stand in for the segments directory so the timeline can be tested without audio."""

    def __init__(self, seconds: float):
        self.seconds = seconds

    def __truediv__(self, name: str) -> "_FakePath":
        return _FakePath(self.seconds)


class _FakePath:
    def __init__(self, seconds: float):
        self.seconds = seconds


@pytest.fixture(autouse=True)
def _stub_wav_seconds(monkeypatch):
    import academic_audio.artifact as artifact

    monkeypatch.setattr(
        artifact, "_wav_seconds", lambda path: path.seconds if isinstance(path, _FakePath) else 0.0
    )


def test_cli_request_embeds_the_format_and_material(tmp_path: Path) -> None:
    out = tmp_path / "request.json"
    result = run_cli(
        "listening", "request", "--review-id", "logic.ch01.s01", "--repo-root", str(FIXTURE_COURSE),
        "--format", "toeic-part2", "--count", "5", "--out", str(out),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["count"] == 5
    assert payload["format"]["id"] == "toeic-part2"
    assert payload["format"]["item"][1] == {"role": "choice", "count": 3, "words": [4, 12]}
    assert "命題は真または偽" in payload["material"]


def test_cli_ingest_writes_script_answers_and_tex(tmp_path: Path) -> None:
    path = _write(tmp_path, _result())
    out_dir = tmp_path / "set"

    result = run_cli(
        "listening", "ingest", "--file", str(path), "--format", "toeic-part2",
        "--out-dir", str(out_dir), "--no-pdf",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["items"] == 1 and payload["segments"] == 4  # "Number 1. question" + choice×3
    assert (out_dir / "dialogue.json").exists()
    assert (out_dir / "answers.json").exists()
    assert (out_dir / "worksheet.tex").exists()
    assert (out_dir / "result.json").exists()  # attach-youtube-url の再入力用に残す


def test_cli_attach_youtube_url_rebuilds_the_worksheet_with_the_url(tmp_path: Path) -> None:
    path = _write(tmp_path, _result())
    out_dir = tmp_path / "set"
    run_cli("listening", "ingest", "--file", str(path), "--format", "toeic-part2", "--out-dir", str(out_dir), "--no-pdf")

    result = run_cli(
        "listening", "attach-youtube-url", "--set-dir", str(out_dir), "--format", "toeic-part2",
        "--youtube-url", "https://youtu.be/xyz789", "--no-pdf",
    )

    assert result.returncode == 0, result.stderr
    tex = (out_dir / "worksheet.tex").read_text(encoding="utf-8")
    assert r"\url{https://youtu.be/xyz789}" in tex


def test_cli_ingest_rejects_a_broken_result(tmp_path: Path) -> None:
    path = _write(tmp_path, _result(answer_index=9))

    result = run_cli("listening", "ingest", "--file", str(path), "--format", "toeic-part2", "--no-pdf")

    assert result.returncode == 1
    assert "範囲外" in result.stderr


def test_cli_ingest_defaults_into_the_data_repo(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ACADEMIC_ENGLISH_DATA_REPO", str(tmp_path / "data-repo"))
    path = _write(tmp_path, _result())

    result = run_cli("listening", "ingest", "--file", str(path), "--format", "toeic-part2", "--no-pdf")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    # 科目リポジトリと同じ形: コード(academic-infra)は生成物を書き出す先を
    # academic-english-data(正本)にデフォルトで向ける。
    assert str(tmp_path / "data-repo" / "listening") in payload["dialogue_json"]


def test_cli_listening_publish_dry_run_needs_no_credentials(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("GDRIVE_OAUTH_CLIENT_ID", raising=False)
    set_dir = tmp_path / "set"
    set_dir.mkdir()
    (set_dir / "worksheet.pdf").write_bytes(b"%PDF-fake")
    (set_dir / "answers.json").write_text(json.dumps({"format": "toeic-part2"}), encoding="utf-8")

    result = run_cli("listening", "publish", "--set-dir", str(set_dir), "--dry-run")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    # 固定の TOEIC/listening 配下に、当日の日付を先頭に付けたファイル名で置く。
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert payload["drive_path"] == f"TOEIC/listening/{today}-set.pdf"


def test_cli_listening_publish_strips_the_generation_timestamp(tmp_path: Path) -> None:
    # new_job_id() のスラッグは既に生成時刻を持つ。当日日付をさらに前置すると
    # "2026-08-02-20260802T...``` のように日付が二重になるので剥がす。
    set_dir = tmp_path / "20260802T072921Z-logic.ch01.s01-toeic-part2"
    set_dir.mkdir()
    (set_dir / "worksheet.pdf").write_bytes(b"%PDF-fake")

    result = run_cli("listening", "publish", "--set-dir", str(set_dir), "--dry-run")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert payload["drive_path"] == f"TOEIC/listening/{today}-logic.ch01.s01-toeic-part2.pdf"


def test_cli_listening_publish_name_overrides_the_dated_default(tmp_path: Path) -> None:
    set_dir = tmp_path / "set"
    set_dir.mkdir()
    (set_dir / "worksheet.pdf").write_bytes(b"%PDF-fake")

    result = run_cli("listening", "publish", "--set-dir", str(set_dir), "--dry-run", "--name", "custom.pdf")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["drive_path"] == "TOEIC/listening/custom.pdf"


def test_cli_listening_publish_requires_the_worksheet(tmp_path: Path) -> None:
    set_dir = tmp_path / "set"
    set_dir.mkdir()

    result = run_cli("listening", "publish", "--set-dir", str(set_dir), "--dry-run")

    assert result.returncode == 1
    assert "worksheet.pdf" in result.stderr
