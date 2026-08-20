"""Gmail送信の共通ロジック（Driveの回収フォルダで所有権未譲渡のファイルをアーカイブした
ときの通知など、academic-infra側から本人へメールを送る用途全般）。

`GDRIVE_OAUTH_*`（Driveスコープのみ）とは別に、`gmail.send`スコープの資格情報が要る
（同じアカウント`ueno.academic.materials@gmail.com`から送るが、スコープが違うので
リフレッシュトークンも別発行になる）。認証は `authorize_gmail_send.py` を一度だけ手動実行。
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from email.mime.text import MIMEText
from pathlib import Path

_LOCAL_SECRETS_FALLBACK = Path.home() / ".config" / "academic-infra" / "gmail-send-secrets.env"
_SCOPES = ("https://www.googleapis.com/auth/gmail.send",)
_TOKEN_URI = "https://oauth2.googleapis.com/token"
_REQUIRED_VARS = (
    "GMAIL_SEND_OAUTH_CLIENT_ID",
    "GMAIL_SEND_OAUTH_CLIENT_SECRET",
    "GMAIL_SEND_OAUTH_REFRESH_TOKEN",
    "GMAIL_SEND_TO",
)


class GmailConfigError(Exception):
    pass


@dataclass(frozen=True)
class GmailNotConfiguredResult:
    reason: str


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


def resolve_credentials(local_secrets_path: Path = _LOCAL_SECRETS_FALLBACK) -> dict[str, str] | None:
    """未設定なら例外を出さず None を返す（通知はbest-effortの付随機能のため）。"""
    local = _load_local_secrets(local_secrets_path)
    resolved = {name: os.environ.get(name, "").strip() or local.get(name, "").strip() for name in _REQUIRED_VARS}
    if any(not value for value in resolved.values()):
        return None
    return resolved


def build_service(credentials_values: dict[str, str]):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    credentials = Credentials(
        token=None,
        refresh_token=credentials_values["GMAIL_SEND_OAUTH_REFRESH_TOKEN"],
        client_id=credentials_values["GMAIL_SEND_OAUTH_CLIENT_ID"],
        client_secret=credentials_values["GMAIL_SEND_OAUTH_CLIENT_SECRET"],
        token_uri=_TOKEN_URI,
        scopes=list(_SCOPES),
    )
    credentials.refresh(Request())
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def send_mail(service, to_address: str, subject: str, body: str) -> str:
    """1通送信し、Gmail上のメッセージIDを返す。"""
    message = MIMEText(body)
    message["to"] = to_address
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    result = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return result["id"]


def try_notify(subject: str, body: str) -> bool:
    """設定済みなら送信し True、未設定なら何もせず False を返す（呼び出し側は必須にしない）。"""
    credentials = resolve_credentials()
    if credentials is None:
        return False
    service = build_service(credentials)
    send_mail(service, credentials["GMAIL_SEND_TO"], subject, body)
    return True
