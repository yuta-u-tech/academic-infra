#!/usr/bin/env python3
"""One-time OAuth authorization to obtain a Google Forms API refresh token.

Run this once, locally, on the machine where you can open a browser:

    python3 scripts/authorize_forms.py --client-secret ~/Downloads/client_secret_XXX.json \
        --out ~/.academic-infra/forms-secrets.env

It opens a browser, asks you to sign in as the account that should own the
created Forms, and grant `forms.body` (create/edit) + `forms.responses.readonly`
(read submitted responses) scopes, then writes the three values Forms
integration reads at runtime:

    FORMS_OAUTH_CLIENT_ID
    FORMS_OAUTH_CLIENT_SECRET
    FORMS_OAUTH_REFRESH_TOKEN

Separate OAuth client from Drive's (scripts/authorize_drive.py) — see
scripts/_forms_common.py for why. Create the client in Google Cloud Console
(APIs & Services → Credentials → OAuth client ID → Desktop app), and enable
"Google Forms API" for the project first.

アクセス制御（招待制の共有）は Forms のスコープではなく Drive 側の権限操作なので、
既存の scripts/authorize_drive.py の資格情報を使う（Forms は Drive 上のファイルのため）。
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

# Must match scripts/_forms_common.py.
_SCOPES = (
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/forms.responses.readonly",
)


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
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
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="値を標準出力せずこのファイルに書く（トークンを画面に出さない）。既定: ~/.academic-infra/forms-secrets.env",
    )
    return parser.parse_args()


def main() -> int:
    arguments = _parse_arguments()
    if not arguments.client_secret.exists():
        print(f"エラー: {arguments.client_secret} がありません。", file=sys.stderr)
        return 1

    flow = InstalledAppFlow.from_client_secrets_file(str(arguments.client_secret), scopes=list(_SCOPES))

    # access_type=offline + prompt=consent forces Google to return a refresh
    # token even on a re-authorization; without prompt=consent a second run for
    # an already-approved client yields no refresh token.
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

    client_config = json.loads(arguments.client_secret.read_text(encoding="utf-8"))
    installed = client_config.get("installed") or client_config.get("web") or {}

    lines = [
        f"FORMS_OAUTH_CLIENT_ID={installed.get('client_id', '')}",
        f"FORMS_OAUTH_CLIENT_SECRET={installed.get('client_secret', '')}",
        f"FORMS_OAUTH_REFRESH_TOKEN={credentials.refresh_token}",
    ]

    out = arguments.out or (Path.home() / ".academic-infra" / "forms-secrets.env")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out.chmod(0o600)
    print(f"認証成功。値を {out} に書き込みました（画面には出していません）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
