#!/usr/bin/env python3
"""One-time OAuth authorization to obtain a Gmail *send* refresh token.

Run this once, locally, on the machine where you can open a browser:

    python3 scripts/authorize_gmail_send.py --client-secret ~/Downloads/client_secret_XXX.json \
        --to youbo0129ueno@gmail.com \
        --out ~/.config/academic-infra/gmail-send-secrets.env

Sign in **as the dedicated materials Gmail** (ueno.academic.materials@gmail.com,
the same account used for GDRIVE_OAUTH_*) and grant "Send email on your behalf"
access. This is a separate scope/refresh-token from Drive — reuse the same GCP
OAuth client (add the gmail.send scope to it in Cloud Console) or create a new one.

`--to` is the address that receives notifications (e.g. when drive_inbox_cli.py
--cleanup falls back to archiving because ownership wasn't transferred).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:  # pragma: no cover
    print(
        "エラー: google-auth-oauthlib が必要です。\n"
        "  pip install google-auth-oauthlib",
        file=sys.stderr,
    )
    raise SystemExit(1)

_SCOPES = ("https://www.googleapis.com/auth/gmail.send",)


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--client-secret", type=Path, required=True)
    parser.add_argument("--to", required=True, help="通知の送り先メールアドレス")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--out", type=Path, default=Path.home() / ".config" / "academic-infra" / "gmail-send-secrets.env",
    )
    return parser.parse_args()


def main() -> int:
    arguments = _parse_arguments()
    if not arguments.client_secret.exists():
        print(f"エラー: {arguments.client_secret} がありません。", file=sys.stderr)
        return 1

    flow = InstalledAppFlow.from_client_secrets_file(str(arguments.client_secret), scopes=list(_SCOPES))
    if arguments.no_browser:
        credentials = flow.run_console(access_type="offline", prompt="consent")
    else:
        credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent", open_browser=True)

    if not credentials.refresh_token:
        print(
            "エラー: リフレッシュトークンが返りませんでした。"
            " 一度 https://myaccount.google.com/permissions でこのアプリの許可を取り消してから再実行してください。",
            file=sys.stderr,
        )
        return 1

    import json
    client_config = json.loads(arguments.client_secret.read_text(encoding="utf-8"))
    installed = client_config.get("installed") or client_config.get("web") or {}

    lines = [
        f"GMAIL_SEND_OAUTH_CLIENT_ID={installed.get('client_id', '')}",
        f"GMAIL_SEND_OAUTH_CLIENT_SECRET={installed.get('client_secret', '')}",
        f"GMAIL_SEND_OAUTH_REFRESH_TOKEN={credentials.refresh_token}",
        f"GMAIL_SEND_TO={arguments.to}",
    ]

    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    arguments.out.chmod(0o600)
    print(f"認証成功。値を {arguments.out} に書き込みました（画面には出していません）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
