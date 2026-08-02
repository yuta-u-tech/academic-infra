from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from academic_audio.engines import MultiSpeakerPiperEngine, TTSEngineError, parse_speaker_map
from academic_audio.formats import FormatError, ListeningFormat, load_format
from academic_audio.items import ItemValidationError, load_passage_result, passage_to_answers, passage_to_script
from academic_audio.worksheet import render_passage_tex

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "scripts" / "academic_audio_cli.py"
FIXTURE_COURSE = ROOT / "tests" / "fixtures" / "audio_course"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(CLI), *args], cwd=ROOT, capture_output=True, text=True)


@pytest.fixture
def part3() -> ListeningFormat:
    return load_format("toeic-part3")


@pytest.fixture
def part4() -> ListeningFormat:
    return load_format("toeic-part4")


def _question(answer_index: int = 0) -> dict:
    return {
        "text": "What are the two speakers mainly discussing here?",
        "choices": ["A scheduling conflict", "An unexpected test result", "A budget proposal", "A new hire"],
        "answer_index": answer_index,
        "explanation": "正解の理由をここに書く。",
    }


def _part3_result(**overrides) -> dict:
    item = {
        "item_id": "item-001",
        "passage": [
            {"speaker": "A", "text": "Did you finish checking the truth table for the new circuit design?"},
            {"speaker": "B", "text": "Almost. I found one row where the output doesn't match what we expected."},
            {"speaker": "A", "text": "That's quite concerning, since we're presenting this design tomorrow morning."},
            {"speaker": "B", "text": "It happens when both inputs are false. The gate outputs true instead."},
        ],
        "questions": [_question(1), _question(0), _question(2)],
        "reason": "テスト用の会話。",
    }
    item.update(overrides)
    return {
        "format": "toeic-part3",
        "title": "テスト会話",
        "source_id": "logic.ch01.s01",
        "source_commit": "test-commit",
        "items": [item],
    }


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "result.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


# --- formats.py: grouping: passage の front matter -----------------------------------


def test_part3_and_part4_are_available() -> None:
    from academic_audio.formats import available_formats

    assert {"toeic-part2", "toeic-part3", "toeic-part4"} <= set(available_formats())


def test_part3_declares_two_speakers(part3: ListeningFormat) -> None:
    assert part3.grouping == "passage"
    assert part3.passage_slot.speakers == 2
    assert part3.question_slot.count == 3
    assert part3.question_slot.choice_count == 4


def test_part4_declares_one_speaker(part4: ListeningFormat) -> None:
    assert part4.passage_slot.speakers == 1


def test_flat_format_still_has_no_passage_slot() -> None:
    part2 = load_format("toeic-part2")

    assert part2.grouping == "flat"
    assert part2.passage_slot is None
    assert part2.question_slot is None


# --- items.py: passage の検証 ----------------------------------------------------------


def test_valid_part3_result_loads(tmp_path: Path, part3: ListeningFormat) -> None:
    passage_set = load_passage_result(_write(tmp_path, _part3_result()), part3)

    assert len(passage_set.items) == 1
    assert len(passage_set.items[0].passage) == 4
    assert len(passage_set.items[0].questions) == 3


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        # 3人目の話者（C）は toeic-part3 では許可されていない
        (lambda d: d["items"][0]["passage"][0].update(speaker="C"), "話者は A, B だけ"),
        # 発話が少なすぎる（4〜8の下限を割る）
        (lambda d: d["items"][0].update(passage=d["items"][0]["passage"][:2]), "発話数が2です"),
        # questions が3問に満たない
        (lambda d: d["items"][0].update(questions=d["items"][0]["questions"][:2]), "3 問必要です"),
        # 選択肢が4個に満たない
        (lambda d: d["items"][0]["questions"][0].update(choices=["A", "B", "C"]), "4 個必要です"),
        (lambda d: d["items"][0]["questions"][0].update(answer_index=9), "範囲外"),
    ],
)
def test_broken_part3_result_says_what_is_wrong(tmp_path: Path, part3: ListeningFormat, mutate, expected: str) -> None:
    data = _part3_result()
    mutate(data)

    with pytest.raises(ItemValidationError, match=expected):
        load_passage_result(_write(tmp_path, data), part3)


def test_passage_becomes_segments_with_speaker_and_role(tmp_path: Path, part3: ListeningFormat) -> None:
    passage_set = load_passage_result(_write(tmp_path, _part3_result()), part3)
    script = passage_to_script(passage_set, part3)

    passage_segments = [s for s in script.segments if s.role == "passage"]
    question_segments = [s for s in script.segments if s.role == "question"]
    number_segments = [s for s in script.segments if s.role == "number"]
    intro_segments = [s for s in script.segments if s.role == "intro"]
    assert [s.speaker for s in passage_segments] == ["A", "B", "A", "B"]
    assert all(s.speaker == "narrator" for s in question_segments)
    assert len(question_segments) == 3
    assert all(s.item_id == "item-001" for s in script.segments)
    # 本番同様の進行: "Questions 1 through 3 refer to the following conversation." →
    # 会話 → ("Number N." → 設問) ×3、設問の後は約8秒のマーク時間。
    assert intro_segments[0].text == "Questions 1 through 3 refer to the following conversation."
    assert [s.text for s in number_segments] == ["Number 1.", "Number 2.", "Number 3."]
    assert all(s.pause == 8.0 for s in question_segments)


def test_passage_answers_never_include_choice_text_from_the_passage(tmp_path: Path, part3: ListeningFormat) -> None:
    passage_set = load_passage_result(_write(tmp_path, _part3_result()), part3)
    answers = passage_to_answers(passage_set)

    assert len(answers["items"][0]["questions"]) == 3
    assert answers["items"][0]["questions"][0]["answer_label"] == "B"


def test_passage_worksheet_hides_the_transcript_from_the_question_page(tmp_path: Path, part3: ListeningFormat) -> None:
    passage_set = load_passage_result(_write(tmp_path, _part3_result()), part3)
    tex = render_passage_tex(passage_set, part3)

    questions, _, answers = tex.partition(r"\section*{スクリプトと解答}")
    # 設問ページに会話の書き起こしを出さない。読んでしまえば聴解にならない。
    assert "Did you finish checking" not in questions
    assert "Did you finish checking" in answers
    assert "A scheduling conflict" in questions


# --- engines.py: 話者ごとの Piper モデル切り替え -----------------------------------------


def test_parse_speaker_map() -> None:
    assert parse_speaker_map("A=/a.onnx,B=/b.onnx") == {"A": "/a.onnx", "B": "/b.onnx"}


def test_parse_speaker_map_rejects_bad_syntax() -> None:
    with pytest.raises(TTSEngineError):
        parse_speaker_map("just-a-name")


def test_multi_speaker_engine_requires_a_voice_map() -> None:
    with pytest.raises(TTSEngineError):
        MultiSpeakerPiperEngine({})


def test_multi_speaker_engine_rejects_an_unmapped_speaker(tmp_path: Path) -> None:
    from academic_audio.models import DialogueSegment

    model = tmp_path / "a.onnx"
    model.write_bytes(b"")
    engine = MultiSpeakerPiperEngine({"A": str(model)})
    segment = DialogueSegment(id="seg-001", speaker="C", text="hello")

    with pytest.raises(TTSEngineError, match="C"):
        engine.render(segment, tmp_path / "out.wav")


def test_multi_speaker_engine_cache_identity_differs_per_speaker_model(tmp_path: Path) -> None:
    """再現テスト: narrator の声だけモデルを差し替えても、同じキャッシュキーのままだと
    renderer.py が古い音声を再利用してしまう不具合があった（実際に起きた）。
    speaker が違えばモデルが違う限りキャッシュキーも変わらないといけない。"""
    from academic_audio.models import DialogueSegment

    model_a = tmp_path / "a.onnx"
    model_b = tmp_path / "b.onnx"
    model_a.write_bytes(b"")
    model_b.write_bytes(b"")
    engine = MultiSpeakerPiperEngine({"A": str(model_a), "narrator": str(model_a)})
    other_engine = MultiSpeakerPiperEngine({"A": str(model_a), "narrator": str(model_b)})
    segment = DialogueSegment(id="seg-001", speaker="narrator", text="Number 1.")

    assert engine.cache_identity(segment) != other_engine.cache_identity(segment)


# --- CLI: request / ingest の grouping: passage 経路 -------------------------------------


def test_cli_request_embeds_passage_and_question_constraints(tmp_path: Path) -> None:
    out = tmp_path / "request.json"

    result = run_cli(
        "listening", "request", "--review-id", "logic.ch01.s01", "--repo-root", str(FIXTURE_COURSE),
        "--format", "toeic-part3", "--count", "2", "--out", str(out),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["format"]["grouping"] == "passage"
    assert payload["format"]["passage"]["speakers"] == 2
    assert payload["format"]["questions"]["count"] == 3
    assert "item" not in payload["format"]


def test_cli_ingest_writes_grouped_script_and_worksheet(tmp_path: Path) -> None:
    path = _write(tmp_path, _part3_result())
    out_dir = tmp_path / "set"

    result = run_cli(
        "listening", "ingest", "--file", str(path), "--format", "toeic-part3",
        "--out-dir", str(out_dir), "--no-pdf",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["items"] == 1
    # intro(Questions...) + 4発話 + (Number + question)×3
    assert payload["segments"] == 11
    assert (out_dir / "worksheet.tex").exists()


def test_cli_ingest_rejects_a_broken_part3_result(tmp_path: Path) -> None:
    data = _part3_result()
    data["items"][0]["passage"][0]["speaker"] = "Z"
    path = _write(tmp_path, data)

    result = run_cli("listening", "ingest", "--file", str(path), "--format", "toeic-part3", "--no-pdf")

    assert result.returncode == 1
    assert "話者は" in result.stderr
