import json
import subprocess
from pathlib import Path

import pytest

import promote_drive_comments as pdc


@pytest.fixture
def finding() -> dict:
    return {
        "index": 1,
        "review_id": "logic.lecture08.implication",
        "title": "含意の説明が誤っている",
        "source_file": "src/chapters/ch08.tex",
        "problem": "P→Qの真理値表の3行目が逆になっている",
        "fix_spec": ["3行目のTをFに直す"],
        "quote": "P→Qが偽になるのはPが真Qが真のときのみ",
        "comment_id": "c1",
        "file_id": "pdf-1",
    }


def test_load_findings_from_list(tmp_path: Path, finding: dict) -> None:
    path = tmp_path / "findings.json"
    path.write_text(json.dumps([finding]), encoding="utf-8")
    assert pdc.load_findings(path) == [finding]


def test_load_findings_from_dict_wrapper(tmp_path: Path, finding: dict) -> None:
    path = tmp_path / "findings.json"
    path.write_text(json.dumps({"findings": [finding]}), encoding="utf-8")
    assert pdc.load_findings(path) == [finding]


def test_load_findings_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(pdc.FindingsError):
        pdc.load_findings(tmp_path / "nonexistent.json")


def test_load_findings_empty_raises(tmp_path: Path) -> None:
    path = tmp_path / "findings.json"
    path.write_text(json.dumps([]), encoding="utf-8")
    with pytest.raises(pdc.FindingsError):
        pdc.load_findings(path)


def test_select_findings_filters_by_pick(finding: dict) -> None:
    other = {**finding, "index": 2}
    result = pdc.select_findings([finding, other], picks=[2])
    assert result == [other]


def test_select_findings_missing_pick_raises(finding: dict) -> None:
    with pytest.raises(pdc.FindingsError):
        pdc.select_findings([finding], picks=[1, 99])


def test_format_issue_body_includes_key_fields(finding: dict) -> None:
    body = pdc.format_issue_body(finding, "yuta-u-tech/Logic")
    assert "yuta-u-tech/Logic" in body
    assert "Drive閲覧者コメント" in body
    assert "src/chapters/ch08.tex" in body
    assert "1. 3行目のTをFに直す" in body
    assert "P→Qが偽になるのはPが真Qが真のときのみ" in body
    assert "上記以外の箇所は触らない" in body


def test_format_issue_body_uses_overrides(finding: dict) -> None:
    finding = {**finding, "forbidden": ["カスタム禁止事項"], "completion_checklist": ["カスタム完了条件"]}
    body = pdc.format_issue_body(finding, "yuta-u-tech/Logic")
    assert "カスタム禁止事項" in body
    assert "カスタム完了条件" in body
    assert "上記以外の箇所は触らない" not in body


def test_mark_processed_appends_and_dedupes(tmp_path: Path) -> None:
    pdc.mark_processed("logic", "c1", state_root=tmp_path)
    pdc.mark_processed("logic", "c2", state_root=tmp_path)
    pdc.mark_processed("logic", "c1", state_root=tmp_path)

    stored = json.loads((tmp_path / "logic" / "processed-comments.json").read_text(encoding="utf-8"))
    assert stored == ["c1", "c2"]


def test_create_issue_returns_url_on_success(monkeypatch, finding: dict) -> None:
    fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="https://github.com/x/y/issues/1\n", stderr="")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake_result)

    url = pdc.create_issue(finding, "yuta-u-tech/Logic")
    assert url == "https://github.com/x/y/issues/1"


def test_create_issue_raises_on_failure(monkeypatch, finding: dict) -> None:
    fake_result = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="gh not authenticated")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake_result)

    with pytest.raises(RuntimeError):
        pdc.create_issue(finding, "yuta-u-tech/Logic")


def test_reply_on_drive_calls_replies_create() -> None:
    calls = []

    class _FakeReplies:
        def create(self, **kwargs):
            calls.append(kwargs)
            return self

        def execute(self):
            return {"id": "reply-1"}

    class _FakeService:
        def replies(self):
            return _FakeReplies()

    pdc.reply_on_drive(_FakeService(), "pdf-1", "c1", "https://github.com/x/y/issues/1")

    assert calls[0]["fileId"] == "pdf-1"
    assert calls[0]["commentId"] == "c1"
    assert "https://github.com/x/y/issues/1" in calls[0]["body"]["content"]
