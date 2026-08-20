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

    # 取得後に片付ける（--cleanupを両コマンドに付けられる）
    python3 scripts/drive_inbox_cli.py fetch --name flashcards.pdf --out /tmp/flashcards.pdf --cleanup

`--cleanup` はまず完全削除を試み、権限不足なら自動で「回収/processed」への移動に
フォールバックする。ユーザー本人がDriveへ直接アップロードしたファイルの所有権は
アップロードした本人に残る仕様のため、通常はこちらのAPI認証情報では削除できない
（2026-08-20、実際に403で確認済み）。**ユーザーがDrive上でそのファイルの所有権を
このアカウント（`GDRIVE_OAUTH_*` の認証先）へ個別に譲渡した場合は削除が成功する**
（実際に確認済み）。自動的な所有権移譲の手段は無い（個人Gmailアカウントでは共有ドライブを
作成できずWorkspace機能も使えない）ため、削除したい場合はユーザーに都度その旨を伝えて
もらう運用になる。
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


def _cleanup_file(service, drive_common, file_id: str, folder_id: str, file_name: str) -> str:
    """削除を試み、権限不足なら「回収/processed」へ移動する。実際に行った処理名を返す。

    削除に失敗した場合（＝ファイルの所有権がまだこちらのアカウントに譲渡されていない）は、
    その旨をメールで通知する（gmail-send-secrets.env が未設定ならbest-effortで無視する。
    詳細は _gmail_common.py 参照）。所有権を譲渡してもらえれば、次回の --cleanup で
    自動的に完全削除される。
    """
    if drive_common.try_delete_file(service, file_id):
        return "deleted"
    archive_id = _archive_folder_id(service, drive_common, folder_id)
    drive_common.move_file(service, file_id, folder_id, archive_id)
    try:
        import _gmail_common as gmail_common
        gmail_common.try_notify(
            subject=f"[回収] {file_name} を処理しました（削除には所有権の譲渡が必要）",
            body=(
                f"「{file_name}」の内容は処理済みです。\n"
                "このファイルはあなたのアカウントが所有しているため、こちらのAPIからは"
                "削除できず「回収/processed」へ移動しました。\n\n"
                "完全に削除したい場合は、Drive上でこのファイルの所有権を "
                "ueno.academic.materials@gmail.com へ譲渡してください。"
                "次回の --cleanup 実行時に自動で削除されます。"
            ),
        )
    except Exception:
        pass  # 通知はbest-effort。失敗してもアーカイブ自体は成功しているので処理を止めない。
    return "archived"


def _cmd_fetch(args: argparse.Namespace) -> int:
    drive_common, service, folder_id = _connect(args)
    files = drive_common.list_files(service, folder_id)
    matches = [f for f in files if f["name"] == args.name]
    if not matches:
        raise SystemExit(f"「{args.folder_name}」に '{args.name}' が見つかりません。")
    file_id = matches[0]["id"]
    out_path = drive_common.download_file(service, file_id, args.out)
    cleanup = _cleanup_file(service, drive_common, file_id, folder_id, args.name) if args.cleanup else None
    print(json.dumps(
        {"downloaded": str(out_path), "file_id": file_id, "cleanup": cleanup},
        ensure_ascii=False, indent=2))
    return 0


def _cmd_fetch_all(args: argparse.Namespace) -> int:
    drive_common, service, folder_id = _connect(args)
    files = drive_common.list_files(service, folder_id)
    downloaded = []
    cleanup_results = {}
    for entry in files:
        out_path = args.out_dir / entry["name"]
        drive_common.download_file(service, entry["id"], out_path)
        downloaded.append(str(out_path))
        if args.cleanup:
            cleanup_results[entry["name"]] = _cleanup_file(
                service, drive_common, entry["id"], folder_id, entry["name"])
    print(json.dumps(
        {"downloaded": downloaded, "cleanup": cleanup_results or None}, ensure_ascii=False, indent=2))
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
        "--cleanup", action="store_true",
        help="取得後、削除を試み、権限不足なら「回収/processed」へ移動する",
    )
    fetch.set_defaults(func=_cmd_fetch)

    fetch_all = sub.add_parser("fetch-all", help="回収フォルダ直下の全ファイルを取得")
    fetch_all.add_argument("--folder-name", default=DEFAULT_FOLDER_NAME)
    fetch_all.add_argument("--parent-id", help="既定は GDRIVE_PARENT_FOLDER_ID")
    fetch_all.add_argument("--out-dir", type=Path, required=True)
    fetch_all.add_argument(
        "--cleanup", action="store_true",
        help="取得後、削除を試み、権限不足なら「回収/processed」へ移動する",
    )
    fetch_all.set_defaults(func=_cmd_fetch_all)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
