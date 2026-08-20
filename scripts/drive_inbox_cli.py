#!/usr/bin/env python3
"""Drive上の「回収」フォルダ（汎用の提出物置き場）を操作する。

TOEIC単語帳のチェック済みPDFに限らず、今後の演習自動採点など「ユーザーがDriveに
アップロードしたファイルをこちらが取りに行って処理する」用途全般で使う想定
（2026-08-19、単語帳のチェック回収をきっかけに新設）。Drive上の共有フォルダ直下
（`GDRIVE_PARENT_FOLDER_ID`）に、他の科目フォルダ（TOEIC/統計学/...）と並ぶ形で
「回収」フォルダを1つ置き、その中はユーザーが自由に使う（サブフォルダを切っても、
直下にそのまま置いてもよい）。

    # 「回収」直下のファイル一覧
    python3 scripts/drive_inbox_cli.py list

    # 特定ファイルをローカルへ取得
    python3 scripts/drive_inbox_cli.py fetch --name flashcards.pdf --out /tmp/flashcards.pdf

    # 直下の全ファイルをまとめて取得
    python3 scripts/drive_inbox_cli.py fetch-all --out-dir /tmp/inbox

    # 取得と同時に「回収/processed」へアーカイブ（--archiveを両コマンドに付けられる）
    python3 scripts/drive_inbox_cli.py fetch --name flashcards.pdf --out /tmp/flashcards.pdf --archive

削除ではなくアーカイブなのは、ユーザー本人がDriveへ直接アップロードしたファイルの所有権は
アップロードした本人に残る仕様のため、こちらのAPI認証情報では削除・ゴミ箱移動ができない
（2026-08-20、実際に403で確認済み）。親フォルダの付け替え（移動）は所有権と無関係に行える
ため、「回収」直下を常に未処理のみにし、処理済みは「回収/processed」へ移すことで実質的な
削除フローの代わりにする。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

DEFAULT_FOLDER_NAME = "回収"


def _resolve_folder_id(service, drive_common, folder_name: str, parent_id: str) -> str:
    folder_names = [part for part in folder_name.split("/") if part]
    folder_id = parent_id
    for name in folder_names:
        folder_id = drive_common.ensure_folder(service, folder_id, name)
    return folder_id


def _connect(args: argparse.Namespace):
    import _drive_common as drive_common

    credentials = drive_common.resolve_credentials()
    parent_id = args.parent_id or credentials.get("GDRIVE_PARENT_FOLDER_ID", "")
    if not parent_id:
        raise ValueError("--parent-id か GDRIVE_PARENT_FOLDER_ID が必要です。")
    service = drive_common.build_service(credentials)
    folder_id = _resolve_folder_id(service, drive_common, args.folder_name, parent_id)
    return drive_common, service, folder_id


def _cmd_list(args: argparse.Namespace) -> int:
    drive_common, service, folder_id = _connect(args)
    files = drive_common.list_files(service, folder_id)
    print(json.dumps({"folder": args.folder_name, "files": files}, ensure_ascii=False, indent=2))
    return 0


def _archive_folder_id(service, drive_common, folder_id: str) -> str:
    return drive_common.ensure_folder(service, folder_id, "processed")


def _cmd_fetch(args: argparse.Namespace) -> int:
    drive_common, service, folder_id = _connect(args)
    files = drive_common.list_files(service, folder_id)
    matches = [f for f in files if f["name"] == args.name]
    if not matches:
        raise SystemExit(f"「{args.folder_name}」に '{args.name}' が見つかりません。")
    file_id = matches[0]["id"]
    out_path = drive_common.download_file(service, file_id, args.out)
    archived = False
    if args.archive:
        archive_id = _archive_folder_id(service, drive_common, folder_id)
        drive_common.move_file(service, file_id, folder_id, archive_id)
        archived = True
    print(json.dumps(
        {"downloaded": str(out_path), "file_id": file_id, "archived": archived},
        ensure_ascii=False, indent=2))
    return 0


def _cmd_fetch_all(args: argparse.Namespace) -> int:
    drive_common, service, folder_id = _connect(args)
    files = drive_common.list_files(service, folder_id)
    downloaded = []
    archive_id = _archive_folder_id(service, drive_common, folder_id) if args.archive else None
    for entry in files:
        out_path = args.out_dir / entry["name"]
        drive_common.download_file(service, entry["id"], out_path)
        downloaded.append(str(out_path))
        if archive_id:
            drive_common.move_file(service, entry["id"], folder_id, archive_id)
    print(json.dumps(
        {"downloaded": downloaded, "archived": args.archive}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    for name, func in (("list", _cmd_list),):
        p = sub.add_parser(name, help="回収フォルダ直下のファイル一覧")
        p.add_argument("--folder-name", default=DEFAULT_FOLDER_NAME, help="Drive上のフォルダパス（既定: 回収）")
        p.add_argument("--parent-id", help="既定は GDRIVE_PARENT_FOLDER_ID")
        p.set_defaults(func=func)

    fetch = sub.add_parser("fetch", help="回収フォルダから指定ファイルを1件取得")
    fetch.add_argument("--folder-name", default=DEFAULT_FOLDER_NAME)
    fetch.add_argument("--parent-id", help="既定は GDRIVE_PARENT_FOLDER_ID")
    fetch.add_argument("--name", required=True, help="Drive上のファイル名")
    fetch.add_argument("--out", type=Path, required=True, help="保存先ローカルパス")
    fetch.add_argument(
        "--archive", action="store_true",
        help="取得後、ファイルを「回収/processed」へ移動する（削除ではなくアーカイブ）",
    )
    fetch.set_defaults(func=_cmd_fetch)

    fetch_all = sub.add_parser("fetch-all", help="回収フォルダ直下の全ファイルを取得")
    fetch_all.add_argument("--folder-name", default=DEFAULT_FOLDER_NAME)
    fetch_all.add_argument("--parent-id", help="既定は GDRIVE_PARENT_FOLDER_ID")
    fetch_all.add_argument("--out-dir", type=Path, required=True)
    fetch_all.add_argument(
        "--archive", action="store_true",
        help="取得後、ファイルを「回収/processed」へ移動する（削除ではなくアーカイブ）",
    )
    fetch_all.set_defaults(func=_cmd_fetch_all)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
