#!/usr/bin/env python3
"""One-time OAuth authorization to obtain a Drive refresh token.

Run this once, locally, on the machine where you can open a browser:

    python3 scripts/authorize_drive.py --client-secret ~/Downloads/client_secret_XXX.json

It opens a browser, asks you to sign in **as the dedicated materials Gmail**
and grant Drive access, then prints the three values to register as GitHub
secrets:

    GDRIVE_OAUTH_CLIENT_ID
    GDRIVE_OAUTH_CLIENT_SECRET
    GDRIVE_OAUTH_REFRESH_TOKEN

The refresh token lets CI act as that user (so uploaded files are owned by, and
counted against, that account's quota — a service account cannot do this on a
consumer Gmail). Treat the printed values like passwords.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:  # pragma: no cover - surfaced at runtime with a clear message
    print(
        "エラー: google-auth-oauthlib が必要です。\n"
        "  pip install google-auth-oauthlib",
        file=sys.stderr,
    )
    raise SystemExit(1)

# Must match update_drive.py. Full drive scope: see the note there.
_SCOPES = ("https://www.googleapis.com/auth/drive",)


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--client-secret",
        type=Path,
        required=True,
        help="GCP で作成した OAuth クライアント (デスクトップ) の JSON パス",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="ブラウザを自動で開かず、URL を表示してコンソールで認証する",
    )
    return parser.parse_args()


def main() -> int:
    arguments = _parse_arguments()
    if not arguments.client_secret.exists():
        print(f"エラー: {arguments.client_secret} がありません。", file=sys.stderr)
        return 1

    flow = InstalledAppFlow.from_client_secrets_file(
        str(arguments.client_secret), scopes=list(_SCOPES)
    )

    # access_type=offline + prompt=consent forces Google to return a refresh
    # token even on a re-authorization; without prompt=consent a second run for
    # an already-approved client yields no refresh token.
    if arguments.no_browser:
        credentials = flow.run_console(access_type="offline", prompt="consent")
    else:
        credentials = flow.run_local_server(
            port=0, access_type="offline", prompt="consent", open_browser=True
        )

    if not credentials.refresh_token:
        print(
            "エラー: リフレッシュトークンが返りませんでした。"
            " 一度 https://myaccount.google.com/permissions でこのアプリの許可を取り消してから再実行してください。",
            file=sys.stderr,
        )
        return 1

    client_config = json.loads(arguments.client_secret.read_text(encoding="utf-8"))
    installed = client_config.get("installed") or client_config.get("web") or {}

    print("\n===== GitHub Secrets に登録する値 =====\n")
    print(f"GDRIVE_OAUTH_CLIENT_ID={installed.get('client_id', '')}")
    print(f"GDRIVE_OAUTH_CLIENT_SECRET={installed.get('client_secret', '')}")
    print(f"GDRIVE_OAUTH_REFRESH_TOKEN={credentials.refresh_token}")
    print("\n(この3つはパスワード同然です。共有しないこと)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
