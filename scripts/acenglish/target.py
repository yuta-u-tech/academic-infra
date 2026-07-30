"""学習対象の解決: 科目名 → リポジトリ → review-manifest.json → セクション本文。

新しいID体系は作らない。学習対象の住所は既存の REVIEW-ID（`dsa.ch02.list.s01`）
そのものを使う（README「REVIEW-ID は変えない」）。

ローカルの科目リポジトリの場所は lecture-capture の `lecture.yml` の `repo_path` を
そのまま読む。同じ情報を2箇所で持つとどちらかが必ず腐るため、新しい設定ファイルは足さない。
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _drive_common import COURSES_YML_PATH, CourseNotFoundError  # noqa: E402

LECTURE_CONFIG_PATH = Path.home() / ".lecture-capture" / "config" / "lecture.yml"


class ManifestNotFoundError(Exception):
    pass


class TargetNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class LearningTarget:
    """1つの学習対象（= sections/*.md 1ファイル）。"""

    review_id: str
    course_id: str
    title: str
    chapter_title: str
    source_file: str
    section_file: str
    source_commit: str
    body: str


def resolve_course_id(name: str, courses_path: Path = COURSES_YML_PATH) -> str:
    """`courses.yml` の id または aliases から course_id を引く。

    `_drive_common.resolve_course` は完全一致の id しか受け付けないが、pm-desk からは
    「データ構造」「statistics」のような口語で来る。SKILL.md が謳っている aliases 解決を
    ここで実装する（既存関数の挙動は変えない）。
    """
    data = yaml.safe_load(courses_path.read_text(encoding="utf-8")) or {}
    entries = data.get("courses") or {}
    needle = name.strip().casefold()

    for course_id, entry in entries.items():
        if course_id.casefold() == needle:
            return course_id
    for course_id, entry in entries.items():
        candidates = [entry.get("course_name", "")] + list(entry.get("aliases") or [])
        if any(str(c).strip().casefold() == needle for c in candidates):
            return course_id

    raise CourseNotFoundError(
        f"courses.yml に科目 '{name}' がありません（登録済み: {', '.join(sorted(entries)) or 'なし'}）。"
    )


def repo_path_for(course_id: str, config_path: Path = LECTURE_CONFIG_PATH) -> Path:
    """科目リポジトリのローカルパス。lecture.yml に無ければ `~/<RepoName>` に落とす。"""
    if config_path.exists():
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        entry = (data.get("courses") or {}).get(course_id) or {}
        raw = entry.get("repo_path")
        if raw:
            return Path(raw).expanduser()

    courses = yaml.safe_load(COURSES_YML_PATH.read_text(encoding="utf-8")) or {}
    entry = (courses.get("courses") or {}).get(course_id)
    if not entry:
        raise CourseNotFoundError(f"courses.yml に科目 '{course_id}' がありません。")
    return Path.home() / str(entry["repository"]).split("/")[-1]


def load_manifest(course_id: str, repo_root: Path | None = None) -> dict:
    """科目リポジトリの `dist/review-manifest.json` を読む。"""
    root = repo_root or repo_path_for(course_id)
    path = root / "dist" / "review-manifest.json"
    if not path.exists():
        raise ManifestNotFoundError(
            f"{path} がありません。先に "
            f"`python3 scripts/build_artifacts.py --repo-root {root}` でビルドしてください。"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def list_targets(course_id: str, repo_root: Path | None = None) -> list[LearningTarget]:
    """PDF に含まれる章のセクションだけを学習対象として列挙する。

    `included_in_pdf` が False の章は配布物に載っていない（`exclude_from_publish` 等）ため、
    学習対象からも外す。手元にしか無い資料から問題を作ると、後で参照できなくなる。
    """
    root = repo_root or repo_path_for(course_id)
    manifest = load_manifest(course_id, root)
    commit = manifest.get("commit", "unknown")
    dist = root / "dist"

    targets: list[LearningTarget] = []
    for chapter in manifest.get("chapters", []):
        if not chapter.get("included_in_pdf", True):
            continue
        for section in chapter.get("sections", []):
            markdown_file = section["markdown_file"]
            path = dist / markdown_file
            if not path.exists():
                continue
            targets.append(
                LearningTarget(
                    review_id=section["review_id"],
                    course_id=manifest.get("course_id", course_id),
                    title=section["title"],
                    chapter_title=chapter["title"],
                    source_file=chapter["source_file"],
                    section_file=markdown_file,
                    source_commit=commit,
                    body=_strip_front_matter(path.read_text(encoding="utf-8")),
                )
            )
    return targets


def get_target(review_id: str, course_id: str | None = None, repo_root: Path | None = None) -> LearningTarget:
    """REVIEW-ID 1件を解決する。course_id 省略時は REVIEW-ID の先頭要素を使う。"""
    resolved = course_id or review_id.split(".")[0]
    for target in list_targets(resolved, repo_root):
        if target.review_id == review_id:
            return target
    raise TargetNotFoundError(f"REVIEW-ID '{review_id}' が {resolved} の manifest にありません。")


def _strip_front_matter(markdown: str) -> str:
    """sections/*.md の YAML front matter を落として本文だけ返す。"""
    if not markdown.startswith("---"):
        return markdown.strip()
    end = markdown.find("\n---", 3)
    if end == -1:
        return markdown.strip()
    return markdown[end + 4 :].strip()
