#!/usr/bin/env python3
"""Drive上の公開PDF (latest.pdf) についた閲覧者コメントを取得する（Issue昇華フローの入力）。

    python3 scripts/fetch_drive_comments.py --course logic

内容の評価（Issue化すべきか）はここではしない（決定論コードで書かない）。このスクリプトは
未処理（既にIssue化済みでない）コメントの一覧をJSONで返すだけで、判断はClaudeが行い、
promote_drive_comments.py で実際にIssue化する。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _drive_common import (  # noqa: E402
    CourseNotFoundError,
    DriveConfigError,
    build_service,
    find_course_pdf_file_id,
    resolve_course,
    resolve_credentials,
)

STATE_ROOT = Path(__file__).resolve().parent.parent / ".state"
_COMMENT_FIELDS = (
    "comments(id,content,author(displayName,emailAddress),createdTime,modifiedTime,"
    "resolved,quotedFileContent(value),replies(id,content,author(displayName),createdTime)),"
    "nextPageToken"
)


def processed_ids(course_id: str, state_root: Path = STATE_ROOT) -> set[str]:
    path = state_root / course_id / "processed-comments.json"
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")))


def list_all_comments(service, file_id: str) -> list[dict]:
    comments: list[dict] = []
    page_token: str | None = None
    while True:
        request_kwargs = {"fileId": file_id, "fields": _COMMENT_FIELDS, "includeDeleted": False}
        if page_token:
            request_kwargs["pageToken"] = page_token
        response = service.comments().list(**request_kwargs).execute()
        comments.extend(response.get("comments", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return comments


def filter_comments(comments: list[dict], processed: set[str], include_resolved: bool) -> list[dict]:
    result = []
    for comment in comments:
        if comment["id"] in processed:
            continue
        if comment.get("resolved") and not include_resolved:
            continue
        result.append(comment)
    return result


def simplify_comment(comment: dict, file_id: str) -> dict:
    return {
        "comment_id": comment["id"],
        "file_id": file_id,
        "author": comment.get("author", {}).get("displayName", "不明"),
        "content": comment.get("content", ""),
        "quoted_text": (comment.get("quotedFileContent") or {}).get("value", ""),
        "created_time": comment.get("createdTime"),
        "resolved": comment.get("resolved", False),
        "replies": [
            {
                "author": reply.get("author", {}).get("displayName", "不明"),
                "content": reply.get("content", ""),
            }
            for reply in comment.get("replies", [])
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course", required=True)
    parser.add_argument("--include-resolved", action="store_true", help="解決済みコメントも含める")
    args = parser.parse_args()

    try:
        course = resolve_course(args.course)
    except CourseNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1

    try:
        credentials_values = resolve_credentials()
        service = build_service(credentials_values)
        pdf_id = find_course_pdf_file_id(service, credentials_values["GDRIVE_PARENT_FOLDER_ID"], course)
        raw_comments = list_all_comments(service, pdf_id)
    except DriveConfigError as e:
        print(str(e), file=sys.stderr)
        return 1

    filtered = filter_comments(raw_comments, processed_ids(course.course_id), args.include_resolved)
    simplified = [simplify_comment(comment, pdf_id) for comment in filtered]

    print(
        json.dumps(
            {"course": course.course_id, "repository": course.repository, "comments": simplified},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
