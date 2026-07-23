#!/usr/bin/env python3
"""Mirror the built artefacts into a Google Drive folder.

    python3 scripts/update_drive.py --dist ./dist --folder-name データ構造とアルゴリズム

Drive holds only the current state: `latest.pdf`, `latest.md`,
`review-manifest.json` and `sections/` are updated in place so that a viewer's
link never changes and ChatGPT's synced connector re-indexes the same file IDs
instead of accumulating duplicates. History lives in git, not here.

Authentication acts *as the owning user* via an OAuth refresh token, not a
service account. A service account has zero Drive storage of its own on a
consumer Gmail account, so uploading into a folder it merely has Editor access
to fails with `storageQuotaExceeded`. Acting as the user means the files are
owned by, and counted against, that user's 15 GB quota. Get the refresh token
once with `scripts/authorize_drive.py`.

Required environment variables:

    GDRIVE_OAUTH_CLIENT_ID       OAuth 2.0 クライアントID
    GDRIVE_OAUTH_CLIENT_SECRET   OAuth 2.0 クライアントシークレット
    GDRIVE_OAUTH_REFRESH_TOKEN   authorize_drive.py で取得したリフレッシュトークン
    GDRIVE_PARENT_FOLDER_ID      Academic Materials フォルダの ID
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
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

# Full drive scope: the parent "Academic Materials" folder is created by hand in
# the browser, and drive.file can only touch app-created files, so it could not
# resolve that folder by ID. This runs on a dedicated Gmail that holds nothing
# but these materials, so full scope grants access to exactly this data anyway.
_SCOPES = ("https://www.googleapis.com/auth/drive",)
_TOKEN_URI = "https://oauth2.googleapis.com/token"
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
    parser.add_argument(
        "--draft-chapter",
        metavar="CHAPTER_STEM",
        help=(
            "指定した章（例: ch01）だけを latest.pdf から切り出し、"
            "親フォルダ (Academic Materials) 直下の 'Drafts' フォルダに"
            "'<科目名>_<章>.pdf' としてアップロードする。"
            "本番の科目フォルダ (latest.pdf/sections 等) には一切触れない。"
        ),
    )
    parser.add_argument(
        "--delete-course-subfolder",
        metavar="NAME",
        help=(
            "科目フォルダ直下のサブフォルダ（例: Drafts）とその中身を削除して終了する。"
            "誤って作った下書きフォルダの後片付け用。"
        ),
    )
    return parser.parse_args()


def _build_service():
    client_id = os.environ.get("GDRIVE_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GDRIVE_OAUTH_CLIENT_SECRET", "").strip()
    refresh_token = os.environ.get("GDRIVE_OAUTH_REFRESH_TOKEN", "").strip()

    missing = [
        name
        for name, value in (
            ("GDRIVE_OAUTH_CLIENT_ID", client_id),
            ("GDRIVE_OAUTH_CLIENT_SECRET", client_secret),
            ("GDRIVE_OAUTH_REFRESH_TOKEN", refresh_token),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(f"OAuth 認証情報が不足しています: {', '.join(missing)}")

    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri=_TOKEN_URI,
        scopes=list(_SCOPES),
    )
    # Exchange the refresh token for an access token up front so a bad/expired
    # token fails here with a clear message instead of mid-upload.
    credentials.refresh(Request())
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


def _upload(service, parent_id: str, path: Path, name: str | None = None) -> str:
    """Create or overwrite `path` (as `name`) under `parent_id`, keeping the file ID stable."""
    drive_name = name or path.name
    mime_type = _MIME_TYPES.get(path.suffix, "application/octet-stream")
    media = MediaFileUpload(str(path), mimetype=mime_type, resumable=False)
    existing = _find_child(service, parent_id, drive_name, None)
    if existing:
        service.files().update(
            fileId=existing, media_body=media, supportsAllDrives=True
        ).execute()
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


def _trash_folder_and_contents(service, parent_id: str, name: str) -> bool:
    """Trash the subfolder `name` under `parent_id`, and everything inside it.

    Trashing the folder alone leaves Drive's own recursive trash behaviour to
    do the rest for a normal folder, but being explicit about the children
    first means this also works for any file `update_drive.py` created there.
    Returns False if no such folder exists.
    """
    folder_id = _find_child(service, parent_id, name, _FOLDER_MIME)
    if folder_id is None:
        return False
    children = (
        service.files()
        .list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields="files(id)",
            pageSize=1000,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
        .get("files", [])
    )
    for child in children:
        service.files().update(
            fileId=child["id"], body={"trashed": True}, supportsAllDrives=True
        ).execute()
    service.files().update(
        fileId=folder_id, body={"trashed": True}, supportsAllDrives=True
    ).execute()
    return True


def _slice_chapter_pdf(dist: Path, chapter_stem: str, tmp_dir: Path) -> Path:
    """Extract the page range for one chapter out of dist/latest.pdf.

    Page numbers come from review-manifest.json (already computed by
    build_artifacts.py from the JPTeX page-start labels), so this stays in
    sync with however the chapter is actually laid out in the PDF.
    """
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError as error:  # pragma: no cover
        raise RuntimeError("pypdf が見つかりません。pip install pypdf") from error

    manifest_path = dist / "review-manifest.json"
    pdf_path = dist / "latest.pdf"
    if not manifest_path.exists() or not pdf_path.exists():
        raise RuntimeError(f"{manifest_path} または {pdf_path} がありません。先にビルドしてください。")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    chapter = next(
        (
            entry
            for entry in manifest.get("chapters", [])
            if Path(entry["source_file"]).stem == chapter_stem
        ),
        None,
    )
    if chapter is None:
        available = ", ".join(Path(e["source_file"]).stem for e in manifest.get("chapters", []))
        raise RuntimeError(f"章 '{chapter_stem}' が manifest にありません。存在する章: {available}")
    page_start, page_end = chapter.get("page_start"), chapter.get("page_end")
    if not page_start or not page_end:
        raise RuntimeError(f"章 '{chapter_stem}' のページ範囲が manifest に記録されていません。")

    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()
    for page_number in range(page_start, page_end + 1):
        writer.add_page(reader.pages[page_number - 1])

    sliced_path = tmp_dir / f"{chapter_stem}.pdf"
    with sliced_path.open("wb") as handle:
        writer.write(handle)
    return sliced_path


_GOODNOTES_MIRROR_SCRIPT = Path.home() / ".claude" / "skills" / "pm-desk" / "scripts" / "goodnotes-mirror.py"


def _mirror_to_goodnotes(pdf_path: Path, folder_name: str) -> None:
    """latest.pdf を GoodNotes 自動インポート監視フォルダへコピーする(best-effort)。

    Drive 上の latest.pdf は同一ファイルIDで上書きされるが、GoodNotesは
    既存ドキュメントへの差分更新に対応していない。共有スクリプト側
    (goodnotes-mirror.py) がページ単位で前回との差分を見て、末尾への
    追記だけなら追記分のみを、既存ページが変わっていれば全体を
    新規ドキュメントとしてミラーする。
    """
    if not _GOODNOTES_MIRROR_SCRIPT.exists():
        return
    stem = re.sub(r"[^\w-]+", "-", folder_name).strip("-") + "-materials"
    try:
        subprocess.run(
            ["python3", str(_GOODNOTES_MIRROR_SCRIPT), str(pdf_path), stem],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, OSError) as error:
        print(f"GoodNotesミラー警告: {error}", file=sys.stderr)


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

        if arguments.delete_course_subfolder:
            course_folder = _ensure_folder(service, arguments.parent_id, arguments.folder_name)
            removed = _trash_folder_and_contents(
                service, course_folder, arguments.delete_course_subfolder
            )
            if removed:
                print(f"削除: {arguments.folder_name}/{arguments.delete_course_subfolder}（中身含む）")
            else:
                print(f"該当なし: {arguments.folder_name}/{arguments.delete_course_subfolder}")
            return 0

        if arguments.draft_chapter:
            with tempfile.TemporaryDirectory() as tmp:
                sliced = _slice_chapter_pdf(arguments.dist, arguments.draft_chapter, Path(tmp))
                drafts_folder = _ensure_folder(service, arguments.parent_id, "Drafts")
                drive_name = f"{arguments.folder_name}_{arguments.draft_chapter}.pdf"
                _upload(service, drafts_folder, sliced, name=drive_name)
                print(f"更新(draft): Drafts/{drive_name}")
            return 0

        course_folder = _ensure_folder(service, arguments.parent_id, arguments.folder_name)

        for name in ("latest.pdf", "latest.md", "review-manifest.json"):
            path = arguments.dist / name
            if path.exists():
                _upload(service, course_folder, path)
                print(f"更新: {arguments.folder_name}/{name}")
                if name == "latest.pdf":
                    _mirror_to_goodnotes(path, arguments.folder_name)

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
