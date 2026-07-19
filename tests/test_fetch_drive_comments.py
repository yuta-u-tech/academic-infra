import json
from pathlib import Path

import fetch_drive_comments as fdc


def test_filter_comments_excludes_processed_and_resolved() -> None:
    comments = [
        {"id": "c1", "resolved": False},
        {"id": "c2", "resolved": True},
        {"id": "c3", "resolved": False},
    ]
    result = fdc.filter_comments(comments, processed={"c3"}, include_resolved=False)
    assert [c["id"] for c in result] == ["c1"]


def test_filter_comments_include_resolved() -> None:
    comments = [{"id": "c1", "resolved": True}]
    result = fdc.filter_comments(comments, processed=set(), include_resolved=True)
    assert [c["id"] for c in result] == ["c1"]


def test_simplify_comment_extracts_fields() -> None:
    raw = {
        "id": "c1",
        "content": "この式は間違っています",
        "author": {"displayName": "山田太郎"},
        "createdTime": "2026-07-19T00:00:00Z",
        "resolved": False,
        "quotedFileContent": {"value": "P → Q"},
        "replies": [{"content": "確認します", "author": {"displayName": "筆者"}}],
    }
    result = fdc.simplify_comment(raw, file_id="pdf-1")
    assert result == {
        "comment_id": "c1",
        "file_id": "pdf-1",
        "author": "山田太郎",
        "content": "この式は間違っています",
        "quoted_text": "P → Q",
        "created_time": "2026-07-19T00:00:00Z",
        "resolved": False,
        "replies": [{"author": "筆者", "content": "確認します"}],
    }


def test_processed_ids_reads_state_file(tmp_path: Path) -> None:
    state_dir = tmp_path / "logic"
    state_dir.mkdir()
    (state_dir / "processed-comments.json").write_text(json.dumps(["c1", "c2"]), encoding="utf-8")

    assert fdc.processed_ids("logic", state_root=tmp_path) == {"c1", "c2"}


def test_processed_ids_missing_file_returns_empty(tmp_path: Path) -> None:
    assert fdc.processed_ids("logic", state_root=tmp_path) == set()


def test_list_all_comments_follows_pagination() -> None:
    class _FakeComments:
        def __init__(self):
            self.calls = []

        def list(self, **kwargs):
            self.calls.append(kwargs)
            return self

        def execute(self):
            if len(self.calls) == 1:
                return {"comments": [{"id": "c1"}], "nextPageToken": "page2"}
            return {"comments": [{"id": "c2"}]}

    class _FakeService:
        def __init__(self):
            self._comments = _FakeComments()

        def comments(self):
            return self._comments

    service = _FakeService()
    result = fdc.list_all_comments(service, "pdf-1")

    assert [c["id"] for c in result] == ["c1", "c2"]
    assert "pageToken" not in service._comments.calls[0]
    assert service._comments.calls[1]["pageToken"] == "page2"
