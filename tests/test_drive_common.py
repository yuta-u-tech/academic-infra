from pathlib import Path

import pytest

import _drive_common as drive_common


@pytest.fixture
def courses_yml(tmp_path: Path) -> Path:
    path = tmp_path / "courses.yml"
    path.write_text(
        """
courses:
  logic:
    course_name: 論理学
    repository: yuta-u-tech/Logic
    drive_folder: 論理学
  dsa:
    course_name: データ構造とアルゴリズム
    repository: yuta-u-tech/Data_Structure_And_Algorithms
    drive_folder: データ構造とアルゴリズム
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return path


def test_resolve_course_returns_entry(courses_yml: Path) -> None:
    course = drive_common.resolve_course("logic", courses_yml)
    assert course.repository == "yuta-u-tech/Logic"
    assert course.drive_folder == "論理学"


def test_resolve_course_missing_raises(courses_yml: Path) -> None:
    with pytest.raises(drive_common.CourseNotFoundError):
        drive_common.resolve_course("nonexistent", courses_yml)


def test_load_local_secrets_parses_key_value(tmp_path: Path) -> None:
    path = tmp_path / "drive-secrets.env"
    path.write_text("# comment\nGDRIVE_OAUTH_CLIENT_ID=abc\nGDRIVE_PARENT_FOLDER_ID=folder123\n", encoding="utf-8")
    values = drive_common._load_local_secrets(path)
    assert values == {"GDRIVE_OAUTH_CLIENT_ID": "abc", "GDRIVE_PARENT_FOLDER_ID": "folder123"}


def test_resolve_credentials_env_priority(monkeypatch, tmp_path: Path) -> None:
    for name in drive_common._REQUIRED_VARS:
        monkeypatch.setenv(name, f"env-{name}")
    values = drive_common.resolve_credentials(tmp_path / "nonexistent.env")
    assert values["GDRIVE_OAUTH_CLIENT_ID"] == "env-GDRIVE_OAUTH_CLIENT_ID"


def test_resolve_credentials_falls_back_to_local_file(monkeypatch, tmp_path: Path) -> None:
    for name in drive_common._REQUIRED_VARS:
        monkeypatch.delenv(name, raising=False)
    secrets_path = tmp_path / "drive-secrets.env"
    secrets_path.write_text(
        "\n".join(f"{name}=local-{name}" for name in drive_common._REQUIRED_VARS), encoding="utf-8"
    )
    values = drive_common.resolve_credentials(secrets_path)
    assert values["GDRIVE_PARENT_FOLDER_ID"] == "local-GDRIVE_PARENT_FOLDER_ID"


def test_resolve_credentials_raises_on_missing(monkeypatch, tmp_path: Path) -> None:
    for name in drive_common._REQUIRED_VARS:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(drive_common.DriveConfigError):
        drive_common.resolve_credentials(tmp_path / "nonexistent.env")


def test_find_course_pdf_file_id_success() -> None:
    calls = []

    class _FakeService:
        def files(self):
            return self

        def list(self, **kwargs):
            calls.append(kwargs["q"])
            return self

        def execute(self):
            if len(calls) == 1:
                return {"files": [{"id": "course-folder-id"}]}
            return {"files": [{"id": "pdf-id"}]}

    course = drive_common.CourseEntry(
        course_id="logic", course_name="論理学", repository="yuta-u-tech/Logic", drive_folder="論理学"
    )
    result = drive_common.find_course_pdf_file_id(_FakeService(), "parent-id", course)
    assert result == "pdf-id"


def test_find_course_pdf_file_id_missing_folder_raises() -> None:
    class _FakeService:
        def files(self):
            return self

        def list(self, **kwargs):
            return self

        def execute(self):
            return {"files": []}

    course = drive_common.CourseEntry(
        course_id="logic", course_name="論理学", repository="yuta-u-tech/Logic", drive_folder="論理学"
    )
    with pytest.raises(drive_common.DriveConfigError):
        drive_common.find_course_pdf_file_id(_FakeService(), "parent-id", course)
