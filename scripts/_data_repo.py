"""Push generated learning data to the private `academic-english-data` repo.

科目リポジトリとコード（academic-infra）を分けているのと同じ形を、英語学習にも適用する。
コード・生成ロジックはここ（public）に置くが、語彙・学習履歴・生成した教材は
private な academic-english-data に置く。詳細は academic-english-data/README.md。
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

DEFAULT_DATA_REPO = Path.home() / "academic-english-data"
_ENV_VAR = "ACADEMIC_ENGLISH_DATA_REPO"
_REPO_URL = "https://github.com/yuta-u-tech/academic-english-data.git"


class DataRepoError(Exception):
    pass


def data_repo_path() -> Path:
    override = os.environ.get(_ENV_VAR)
    return Path(override) if override else DEFAULT_DATA_REPO


def require_data_repo(repo: Path | None = None) -> Path:
    path = repo or data_repo_path()
    if not (path / ".git").is_dir():
        raise DataRepoError(
            f"{path} が無いか git リポジトリではありません。"
            f"`git clone {_REPO_URL} {path}` してください"
            f"（{_ENV_VAR} で別の場所を指すこともできます）。"
        )
    return path


def commit_and_push(repo: Path, paths: list[Path], message: str) -> bool:
    """Stage `paths`, commit if there is a diff, and push. Returns whether a commit was made."""
    require_data_repo(repo)
    relative = [str(path.relative_to(repo)) for path in paths]
    _run(["git", "add", *relative], cwd=repo)
    unchanged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo).returncode == 0
    if unchanged:
        return False
    _run(["git", "commit", "-m", message], cwd=repo)
    _run(["git", "push"], cwd=repo)
    return True


def _run(command: list[str], cwd: Path) -> None:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise DataRepoError(completed.stderr.strip() or completed.stdout.strip() or " ".join(command))
