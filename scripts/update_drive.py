#!/usr/bin/env python3
"""Mirror the built artefacts into a Google Drive folder.

    python3 scripts/update_drive.py --dist ./dist --folder-name データ構造とアルゴリズム

Drive holds only the current state: `latest.pdf`, `latest.md`,
`review-manifest.json` and `sections/` are updated in place so that a viewer's
link never changes and ChatGPT's synced connector re-indexes the same file IDs
instead of accumulating duplicates. History lives in git, not here.

Authentication uses a service account supplied through the
GDRIVE_SERVICE_ACCOUNT_JSON environment variable (the raw JSON, not a path).
The parent folder must be shared with the service account's email as Editor.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload
except ImportError:  # pragma: no cover - surfaced at runtime with a clear message
    print(
        "エラー: Google API クライアントが見つかりません。\n"
        "  pip install google-api-python-client google-auth",
        file=sys.stderr,
    )
    raise SystemExit(1)

_SCOPES = ("https://www.googleapis.com/auth/drive",)
_FOLDER_MIME = "application/vnd.google-apps.folder"
_MIME_TYPES = {".pdf": "application/pdf", ".md": "text/markdown", ".json": "application/json"}


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, required=True, help="成果物ディレクトリ")
    parser.add_argument("--folder-name", required=True, help="Drive 上の科目フォルダ名")
    parser.add_argument(
        "--parent-id",
        default=os.environ.get("GDRIVE_PARENT_FOLDER_ID", ""),
        help="親フォルダID (Academic Materials)。GDRIVE_PARENT_FOLDER_ID でも可",
    )
    return parser.parse_args()


def _build_service():
    raw = os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        raise RuntimeError("GDRIVE_SERVICE_ACCOUNT_JSON が設定されていません。")
    try:
        info = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"GDRIVE_SERVICE_ACCOUNT_JSON をJSONとして読めません: {error}") from error
    credentials = Credentials.from_service_account_info(info, scopes=list(_SCOPES))
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def _escape(name: str) -> str:
    return name.replace("\\", "\\\\").replace("'", "\\'")


def _find_child(service, parent_id: str, name: str, mime_type: str | None) -> str | None:
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


def _ensure_folder(service, parent_id: str, name: str) -> str:
    existing = _find_child(service, parent_id, name, _FOLDER_MIME)
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


def _prune(service, parent_id: str, keep: set[str]) -> list[str]:
    """Trash files under `parent_id` whose names are not in `keep`.

    Without this, a section deleted from the TeX would linger in Drive forever
    and keep being answered from as though it were current.
    """
    response = (
        service.files()
        .list(
            q=f"'{parent_id}' in parents and trashed = false",
            fields="files(id, name)",
            pageSize=1000,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    removed: list[str] = []
    for file in response.get("files", []):
        if file["name"] in keep:
            continue
        service.files().update(
            fileId=file["id"], body={"trashed": True}, supportsAllDrives=True
        ).execute()
        removed.append(file["name"])
    return removed


def _upload(service, parent_id: str, path: Path) -> str:
    """Create or overwrite `path` under `parent_id`, keeping the file ID stable."""
    mime_type = _MIME_TYPES.get(path.suffix, "application/octet-stream")
    media = MediaFileUpload(str(path), mimetype=mime_type, resumable=False)
    existing = _find_child(service, parent_id, path.name, None)
    if existing:
        service.files().update(
            fileId=existing, media_body=media, supportsAllDrives=True
        ).execute()
        return existing
    created = (
        service.files()
        .create(
            body={"name": path.name, "parents": [parent_id]},
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        )
        .execute()
    )
    return created["id"]


def main() -> int:
    arguments = _parse_arguments()
    if not arguments.parent_id:
        print("エラー: --parent-id か GDRIVE_PARENT_FOLDER_ID が必要です。", file=sys.stderr)
        return 1
    if not arguments.dist.is_dir():
        print(f"エラー: {arguments.dist} がありません。先に build_artifacts.py を実行してください。", file=sys.stderr)
        return 1

    try:
        service = _build_service()
        course_folder = _ensure_folder(service, arguments.parent_id, arguments.folder_name)

        for name in ("latest.pdf", "latest.md", "review-manifest.json"):
            path = arguments.dist / name
            if path.exists():
                _upload(service, course_folder, path)
                print(f"更新: {arguments.folder_name}/{name}")

        sections_dir = arguments.dist / "sections"
        if sections_dir.is_dir():
            drive_sections = _ensure_folder(service, course_folder, "sections")
            local_names = {path.name for path in sorted(sections_dir.glob("*.md"))}
            for path in sorted(sections_dir.glob("*.md")):
                _upload(service, drive_sections, path)
            print(f"更新: {arguments.folder_name}/sections/ ({len(local_names)} ファイル)")

            for stale in _prune(service, drive_sections, local_names):
                print(f"削除: {arguments.folder_name}/sections/{stale}")
    except (RuntimeError, HttpError) as error:
        print(f"Drive 更新エラー: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
