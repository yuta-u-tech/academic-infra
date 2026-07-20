"""Drive OAuth・courses.yml解決・フォルダ/ファイル探索の共通ロジック。

fetch_drive_comments.py / promote_drive_comments.py から共有される。
Drive OAuthは update_drive.py と同じ資格情報（GDRIVE_OAUTH_*, 環境変数優先）を使う。
ローカル実行（CIではない）ではこの4変数が環境変数に無いことが多いため、
~/.lecture-capture/config/drive-secrets.env にフォールバックする
（academic-infraの資料とlecture-captureの講義Draftは同一の
"Academic Materials" Drive アカウント/OAuthアプリを共有しているため、
二重に秘密情報ファイルを持たずこれを流用する）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

COURSES_YML_PATH = Path(__file__).resolve().parent.parent / "courses.yml"
_LOCAL_SECRETS_FALLBACK = Path.home() / ".lecture-capture" / "config" / "drive-secrets.env"
_SCOPES = ("https://www.googleapis.com/auth/drive",)
_TOKEN_URI = "https://oauth2.googleapis.com/token"
_FOLDER_MIME = "application/vnd.google-apps.folder"
_REQUIRED_VARS = (
    "GDRIVE_OAUTH_CLIENT_ID",
    "GDRIVE_OAUTH_CLIENT_SECRET",
    "GDRIVE_OAUTH_REFRESH_TOKEN",
    "GDRIVE_PARENT_FOLDER_ID",
)


class DriveConfigError(Exception):
    pass


class CourseNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class CourseEntry:
    course_id: str
    course_name: str
    repository: str
    drive_folder: str


def load_courses(path: Path = COURSES_YML_PATH) -> dict[str, CourseEntry]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    courses: dict[str, CourseEntry] = {}
    for course_id, entry in (data.get("courses") or {}).items():
        courses[course_id] = CourseEntry(
            course_id=course_id,
            course_name=entry.get("course_name", course_id),
            repository=entry["repository"],
            drive_folder=entry["drive_folder"],
        )
    return courses


def resolve_course(course_id: str, path: Path = COURSES_YML_PATH) -> CourseEntry:
    courses = load_courses(path)
    if course_id not in courses:
        raise CourseNotFoundError(
            f"courses.yml に科目 '{course_id}' がありません（登録済み: {', '.join(sorted(courses)) or 'なし'}）。"
        )
    return courses[course_id]


def _load_local_secrets(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def resolve_credentials(local_secrets_path: Path = _LOCAL_SECRETS_FALLBACK) -> dict[str, str]:
    local = _load_local_secrets(local_secrets_path)
    resolved = {name: os.environ.get(name, "").strip() or local.get(name, "").strip() for name in _REQUIRED_VARS}
    missing = [name for name, value in resolved.items() if not value]
    if missing:
        raise DriveConfigError(
            "Drive 認証情報が不足しています: "
            f"{', '.join(missing)}。環境変数か {local_secrets_path} に設定してください。"
        )
    return resolved


def build_service(credentials_values: dict[str, str]):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    credentials = Credentials(
        token=None,
        refresh_token=credentials_values["GDRIVE_OAUTH_REFRESH_TOKEN"],
        client_id=credentials_values["GDRIVE_OAUTH_CLIENT_ID"],
        client_secret=credentials_values["GDRIVE_OAUTH_CLIENT_SECRET"],
        token_uri=_TOKEN_URI,
        scopes=list(_SCOPES),
    )
    credentials.refresh(Request())
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def _escape(name: str) -> str:
    return name.replace("\\", "\\\\").replace("'", "\\'")


def find_child(service, parent_id: str, name: str, mime_type: str | None) -> str | None:
    clauses = [f"name = '{_escape(name)}'", f"'{parent_id}' in parents", "trashed = false"]
    if mime_type:
        clauses.append(f"mimeType = '{mime_type}'")
    response = (
        service.files()
        .list(
            q=" and ".join(clauses),
            fields="files(id)",
            pageSize=1,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    files = response.get("files", [])
    return files[0]["id"] if files else None


def ensure_folder(service, parent_id: str, name: str) -> str:
    existing = find_child(service, parent_id, name, _FOLDER_MIME)
    if existing:
        return existing
    created = (
        service.files()
        .create(
            body={"name": name, "mimeType": _FOLDER_MIME, "parents": [parent_id]},
            fields="id",
            supportsAllDrives=True,
        )
        .execute()
    )
    return created["id"]


def upload_named(service, parent_id: str, local_path: Path, drive_name: str, mime_type: str) -> str:
    """`local_path` の中身を `drive_name` という名前で作成/上書きする(ファイルIDは維持)。"""
    from googleapiclient.http import MediaFileUpload

    media = MediaFileUpload(str(local_path), mimetype=mime_type, resumable=False)
    existing = find_child(service, parent_id, drive_name, None)
    if existing:
        service.files().update(fileId=existing, media_body=media, supportsAllDrives=True).execute()
        return existing
    created = (
        service.files()
        .create(
            body={"name": drive_name, "parents": [parent_id]},
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        )
        .execute()
    )
    return created["id"]


def upload_text(service, parent_id: str, drive_name: str, content: str) -> str:
    """短いテキスト(フラグ値等)を `drive_name` という名前で作成/上書きする。"""
    import io

    from googleapiclient.http import MediaIoBaseUpload

    media = MediaIoBaseUpload(io.BytesIO(content.encode("utf-8")), mimetype="text/plain", resumable=False)
    existing = find_child(service, parent_id, drive_name, None)
    if existing:
        service.files().update(fileId=existing, media_body=media, supportsAllDrives=True).execute()
        return existing
    created = (
        service.files()
        .create(
            body={"name": drive_name, "parents": [parent_id]},
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        )
        .execute()
    )
    return created["id"]


def find_course_pdf_file_id(service, parent_folder_id: str, course: CourseEntry) -> str:
    course_folder_id = find_child(service, parent_folder_id, course.drive_folder, _FOLDER_MIME)
    if course_folder_id is None:
        raise DriveConfigError(f"Drive上に科目フォルダが見つかりません: {course.drive_folder}")
    pdf_id = find_child(service, course_folder_id, "latest.pdf", None)
    if pdf_id is None:
        raise DriveConfigError(f"{course.drive_folder}/latest.pdf が見つかりません。先に公開してください。")
    return pdf_id
