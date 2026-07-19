#!/usr/bin/env python3
"""Claudeが構造化したDriveコメントの中から選んだものをGitHub Issueへ昇華する。

    python3 scripts/promote_drive_comments.py --course logic --findings /path/to/findings.json --pick 1,3

findings.json は Claude が書く（templates/review-issue.md 形式、academic-infra/scripts/
fetch_drive_comments.py の出力する comment_id / file_id を含める）。内容の要約・番号付け・
Issue化すべきかの判断は Claude の仕事で、このスクリプトは「選ばれたものを機械的にIssue化し、
Driveのコメントへ返信し、処理済みとして記録する」だけを担う。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _drive_common import (  # noqa: E402
    CourseNotFoundError,
    DriveConfigError,
    build_service,
    resolve_course,
    resolve_credentials,
)

STATE_ROOT = Path(__file__).resolve().parent.parent / ".state"

_DEFAULT_FORBIDDEN = (
    "上記以外の箇所は触らない",
    "既存の記号体系を変えない",
    "情報量を減らさない（要約・削除をしない）",
    "新しい環境・パッケージを追加しない",
)
_DEFAULT_CHECKLIST = (
    "修正が反映されている",
    "`latexmk -lualatex src/main.tex` が通る",
    "REVIEW-ID ヘッダが残っている",
    "上記「変更禁止事項」に反する差分がない",
)
_DEFAULT_LABELS = ("review", "needs-decision")


class FindingsError(Exception):
    pass


def load_findings(path: Path) -> list[dict]:
    if not path.exists():
        raise FindingsError(f"{path} がありません。")
    data = json.loads(path.read_text(encoding="utf-8"))
    findings = data.get("findings", data) if isinstance(data, dict) else data
    if not findings:
        raise FindingsError(f"{path} に findings がありません。")
    return findings


def format_issue_body(finding: dict, repository: str) -> str:
    """templates/review-issue.md のBody形式で1件分を組み立てる。"""
    fix_spec = "\n".join(f"{i}. {step}" for i, step in enumerate(finding["fix_spec"], start=1))
    forbidden = "\n".join(f"- {item}" for item in finding.get("forbidden") or _DEFAULT_FORBIDDEN)
    checklist = "\n".join(f"- [ ] {item}" for item in finding.get("completion_checklist") or _DEFAULT_CHECKLIST)
    pdf_page = finding.get("pdf_page", "(未記入)")
    quote = finding.get("quote", "")
    quote_block = f"\n> {quote}\n" if quote else ""

    return f"""## 対象

| 項目 | 値 |
|---|---|
| Repository | {repository} |
| Source | Drive閲覧者コメント |
| Review ID | {finding["review_id"]} |
| Source File | {finding.get("source_file", "(未確定)")} |
| PDF Page | {pdf_page} |

## 問題

{finding["problem"]}
{quote_block}
## 修正仕様

{fix_spec}

## 変更禁止事項

{forbidden}

## 完了条件

{checklist}
"""


def select_findings(findings: list[dict], picks: list[int]) -> list[dict]:
    selected = [f for f in findings if f.get("index") in picks]
    missing = set(picks) - {f.get("index") for f in findings}
    if missing:
        raise FindingsError(f"指定された番号がfindingsにありません: {sorted(missing)}")
    return selected


def mark_processed(course_id: str, comment_id: str, state_root: Path = STATE_ROOT) -> None:
    state_dir = state_root / course_id
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "processed-comments.json"
    existing = set(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else set()
    existing.add(comment_id)
    path.write_text(json.dumps(sorted(existing), ensure_ascii=False, indent=2), encoding="utf-8")


def create_issue(finding: dict, repository: str) -> str:
    title = f"[{finding['review_id']}] {finding['title']}"
    body = format_issue_body(finding, repository)
    labels = finding.get("labels") or list(_DEFAULT_LABELS)
    result = subprocess.run(
        [
            "gh", "issue", "create",
            "--repo", repository,
            "--title", title,
            "--body", body,
            "--label", ",".join(labels),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Issue作成に失敗しました ({finding['review_id']}): {result.stderr}")
    return result.stdout.strip()


def reply_on_drive(service, file_id: str, comment_id: str, issue_url: str) -> None:
    service.replies().create(
        fileId=file_id,
        commentId=comment_id,
        body={"content": f"Issue化しました: {issue_url}"},
        fields="id",
    ).execute()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course", required=True)
    parser.add_argument("--findings", type=Path, required=True)
    parser.add_argument("--pick", required=True, help="例: 1,3,5")
    parser.add_argument("--no-drive-reply", action="store_true", help="Driveへの返信をスキップする")
    args = parser.parse_args()

    try:
        course = resolve_course(args.course)
    except CourseNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1

    try:
        findings = load_findings(args.findings)
        picks = [int(p) for p in args.pick.split(",")]
        selected = select_findings(findings, picks)
    except FindingsError as e:
        print(str(e), file=sys.stderr)
        return 1

    service = None
    if not args.no_drive_reply:
        try:
            credentials_values = resolve_credentials()
            service = build_service(credentials_values)
        except DriveConfigError as e:
            print(f"警告: Drive認証に失敗したため返信はスキップします: {e}", file=sys.stderr)

    exit_code = 0
    for finding in selected:
        try:
            url = create_issue(finding, course.repository)
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            exit_code = 1
            continue
        print(f"Issue作成: {url}")

        comment_id = finding.get("comment_id")
        if not comment_id:
            continue
        mark_processed(course.course_id, comment_id)
        if service is None:
            continue
        file_id = finding.get("file_id")
        if not file_id:
            continue
        try:
            reply_on_drive(service, file_id, comment_id, url)
            print(f"Drive返信: {comment_id} -> {url}")
        except Exception as e:  # noqa: BLE001 - Drive返信の失敗はIssue作成成功を握りつぶさず警告に留める
            print(f"警告: Drive返信に失敗しました: {e}", file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
