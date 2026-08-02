from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest

import academic_audio_cli
from academic_audio.vocab import DECKS, VocabFetchError, sample_terms

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "scripts" / "academic_audio_cli.py"
FIXTURE_COURSE = ROOT / "tests" / "fixtures" / "audio_course"

_FAKE_DECK = {
    "terms": [
        {"term": "anyway", "definition": "とにかく", "example": "Anyway, let's try."},
        {"term": "following", "definition": "次の", "example": "Following the speech, ..."},
        {"term": "regarding", "definition": "〜に関して", "example": "Regarding your request, ..."},
    ]
}


class _FakeResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_sample_terms_rejects_an_unknown_deck() -> None:
    with pytest.raises(VocabFetchError, match="未知のデッキ"):
        sample_terms("not-a-real-deck", 3)


def test_sample_terms_returns_the_requested_count(monkeypatch) -> None:
    monkeypatch.setattr("academic_audio.vocab.urllib.request.urlopen", lambda *a, **k: _FakeResponse(_FAKE_DECK))

    terms = sample_terms(DECKS[0], 2, seed=1)

    assert len(terms) == 2
    assert {term["term"] for term in terms} <= {"anyway", "following", "regarding"}


def test_sample_terms_caps_at_the_deck_size(monkeypatch) -> None:
    monkeypatch.setattr("academic_audio.vocab.urllib.request.urlopen", lambda *a, **k: _FakeResponse(_FAKE_DECK))

    terms = sample_terms(DECKS[0], 999)

    assert len(terms) == 3


def test_sample_terms_reports_a_fetch_failure(monkeypatch) -> None:
    import urllib.error

    def _raise(*args, **kwargs):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr("academic_audio.vocab.urllib.request.urlopen", _raise)

    with pytest.raises(VocabFetchError, match="取得できません"):
        sample_terms(DECKS[0], 2)


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(CLI), *args], cwd=ROOT, capture_output=True, text=True)


def test_cli_request_embeds_sampled_vocabulary(tmp_path: Path, monkeypatch) -> None:
    # サブプロセス越しだと monkeypatch が別プロセスに効かず実ネットワークを叩いてしまうため、
    # ここだけは CLI モジュールをプロセス内で直接呼ぶ。
    monkeypatch.setattr("academic_audio.vocab.urllib.request.urlopen", lambda *a, **k: _FakeResponse(_FAKE_DECK))
    out = tmp_path / "request.json"
    args = argparse.Namespace(
        review_id="logic.ch01.s01", source=None, repo_root=FIXTURE_COURSE, course=None,
        format="toeic-part2", count=5, out=out, vocab_deck="words1-400", vocab_count=2,
    )

    exit_code = academic_audio_cli._cmd_listening_request(args)

    assert exit_code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["vocabulary"]["deck"] == "words1-400"
    assert len(payload["vocabulary"]["terms"]) == 2
    assert any("vocabulary" in instruction for instruction in payload["instructions"])


def test_cli_request_without_vocab_deck_omits_vocabulary(tmp_path: Path) -> None:
    out = tmp_path / "request.json"

    result = run_cli(
        "listening", "request", "--review-id", "logic.ch01.s01", "--repo-root", str(FIXTURE_COURSE),
        "--format", "toeic-part2", "--count", "5", "--out", str(out),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert "vocabulary" not in payload
