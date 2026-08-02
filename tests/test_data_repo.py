from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from _data_repo import DataRepoError, commit_and_push, require_data_repo


def _init_repo_with_remote(tmp_path: Path) -> Path:
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--quiet", "--bare", str(bare)], check=True)
    repo = tmp_path / "clone"
    subprocess.run(["git", "clone", "--quiet", str(bare), str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    # 空リポジトリだと push 先ブランチが無くて紛らわしいので、最初のコミットを作っておく。
    (repo / "README.md").write_text("seed", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "seed"], cwd=repo, check=True)
    subprocess.run(["git", "push", "--quiet"], cwd=repo, check=True)
    return repo


def test_require_data_repo_rejects_a_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(DataRepoError, match="git clone"):
        require_data_repo(tmp_path / "does-not-exist")


def test_commit_and_push_stages_commits_and_pushes(tmp_path: Path) -> None:
    repo = _init_repo_with_remote(tmp_path)
    (repo / "backups").mkdir()
    snapshot = repo / "backups" / "english-20260802.db"
    snapshot.write_bytes(b"fake sqlite bytes")

    pushed = commit_and_push(repo, [snapshot], "backup: english-20260802.db")

    assert pushed is True
    log = subprocess.run(["git", "log", "--oneline"], cwd=repo, capture_output=True, text=True).stdout
    assert "backup: english-20260802.db" in log
    # push が実際に届いていること（bare origin の HEAD がこのコミットになっている）。
    remote_log = subprocess.run(
        ["git", "log", "--oneline", "origin/main"], cwd=repo, capture_output=True, text=True
    ).stdout
    assert "backup: english-20260802.db" in remote_log


def test_commit_and_push_is_a_no_op_without_a_diff(tmp_path: Path) -> None:
    repo = _init_repo_with_remote(tmp_path)
    (repo / "backups").mkdir()
    snapshot = repo / "backups" / "english-20260802.db"
    snapshot.write_bytes(b"same bytes")
    commit_and_push(repo, [snapshot], "backup: first")

    pushed_again = commit_and_push(repo, [snapshot], "backup: no-op")

    assert pushed_again is False
    log = subprocess.run(["git", "log", "--oneline"], cwd=repo, capture_output=True, text=True).stdout
    assert "backup: no-op" not in log
