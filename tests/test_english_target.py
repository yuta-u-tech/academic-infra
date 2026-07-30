"""学習対象の解決: 既存の courses.yml / review-manifest.json / sections をそのまま使う。"""

import json

import pytest
import yaml

from acenglish.target import (
    ManifestNotFoundError,
    TargetNotFoundError,
    get_target,
    list_targets,
    repo_path_for,
    resolve_course_id,
)
from _drive_common import CourseNotFoundError

MANIFEST = {
    "manifest_version": 1,
    "commit": "abc123",
    "course_id": "dsa",
    "course_name": "データ構造とアルゴリズム",
    "chapters": [
        {
            "review_id": "dsa.ch02.list",
            "title": "リスト構造",
            "source_file": "src/chapters/ch02.tex",
            "included_in_pdf": True,
            "sections": [
                {"review_id": "dsa.ch02.list.s01", "title": "線形リスト",
                 "markdown_file": "sections/ch02-01.md"},
            ],
        },
        {
            "review_id": "dsa.ch99.private",
            "title": "配布対象外",
            "source_file": "src/chapters/ch99.tex",
            "included_in_pdf": False,
            "sections": [
                {"review_id": "dsa.ch99.private.s01", "title": "内部メモ",
                 "markdown_file": "sections/ch99-01.md"},
            ],
        },
    ],
}

SECTION_MD = """---
review_id: dsa.ch02.list.s01
title: "線形リスト"
---

# 線形リスト

先頭から順にたどる。
"""


@pytest.fixture
def repo(tmp_path):
    dist = tmp_path / "dist" / "sections"
    dist.mkdir(parents=True)
    (tmp_path / "dist" / "review-manifest.json").write_text(
        json.dumps(MANIFEST, ensure_ascii=False), encoding="utf-8"
    )
    (dist / "ch02-01.md").write_text(SECTION_MD, encoding="utf-8")
    (dist / "ch99-01.md").write_text(SECTION_MD, encoding="utf-8")
    return tmp_path


def test_course_ids_resolve_from_aliases():
    assert resolve_course_id("dsa") == "dsa"
    assert resolve_course_id("データ構造") == "dsa"
    assert resolve_course_id("Algorithms") == "dsa"
    assert resolve_course_id("統計学") == "statistics"


def test_an_unknown_course_names_the_registered_ones():
    with pytest.raises(CourseNotFoundError, match="登録済み"):
        resolve_course_id("存在しない科目")


def test_every_registered_course_has_a_local_repo_path():
    """courses.yml の全科目が解決できること（lecture.yml に無ければ ~/<RepoName>）。"""
    courses = yaml.safe_load(
        (__import__("pathlib").Path(__file__).resolve().parent.parent / "courses.yml").read_text(
            encoding="utf-8"
        )
    )["courses"]
    for course_id in courses:
        assert repo_path_for(course_id).is_absolute()


def test_sections_become_learning_targets(repo):
    targets = list_targets("dsa", repo)
    assert [t.review_id for t in targets] == ["dsa.ch02.list.s01"]


def test_chapters_excluded_from_the_pdf_are_not_studied(repo):
    """配布物に無い資料から問題を作ると、あとで参照できなくなる。"""
    assert all("ch99" not in t.review_id for t in list_targets("dsa", repo))


def test_front_matter_is_stripped_from_the_body(repo):
    body = list_targets("dsa", repo)[0].body
    assert body.startswith("# 線形リスト")
    assert "review_id:" not in body


def test_targets_carry_the_manifest_commit(repo):
    assert list_targets("dsa", repo)[0].source_commit == "abc123"


def test_get_target_finds_one_review_id(repo):
    assert get_target("dsa.ch02.list.s01", "dsa", repo).title == "線形リスト"


def test_an_unknown_review_id_is_an_error(repo):
    with pytest.raises(TargetNotFoundError):
        get_target("dsa.ch02.list.s99", "dsa", repo)


def test_a_missing_manifest_tells_you_to_build(tmp_path):
    with pytest.raises(ManifestNotFoundError, match="build_artifacts.py"):
        list_targets("dsa", tmp_path)
