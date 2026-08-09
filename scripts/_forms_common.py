"""Google Forms API OAuth. _youtube_common.py と同じ形。

Forms は Drive 上のファイルとして扱われるが、ファイル共有範囲の変更（招待制の
アクセス制御）は既存の _drive_common.py（drive スコープを既に持つ）を流用する。
このモジュールは Forms 自体の作成・編集・回答読み取りに絞ったスコープだけを持つ、
Drive とは別の OAuth クライアントを扱う（YouTube と Drive を分けているのと同じ理由 —
スコープを必要最小限に保つ）。
"""
from __future__ import annotations

import os
from pathlib import Path

_LOCAL_SECRETS_FALLBACK = Path.home() / ".academic-infra" / "forms-secrets.env"
_SCOPES = (
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/forms.responses.readonly",
)
_TOKEN_URI = "https://oauth2.googleapis.com/token"
_REQUIRED_VARS = (
    "FORMS_OAUTH_CLIENT_ID",
    "FORMS_OAUTH_CLIENT_SECRET",
    "FORMS_OAUTH_REFRESH_TOKEN",
)


class FormsConfigError(Exception):
    pass


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


def resolve_credentials(local_secrets_path: Path = _LOCAL_SECRETS_FALLBACK) -> dict[str, str]:
    local = _load_local_secrets(local_secrets_path)
    resolved = {name: os.environ.get(name, "").strip() or local.get(name, "").strip() for name in _REQUIRED_VARS}
    missing = [name for name, value in resolved.items() if not value]
    if missing:
        raise FormsConfigError(
            "Forms 認証情報が不足しています: "
            f"{', '.join(missing)}。scripts/authorize_forms.py で取得し、環境変数か "
            f"{local_secrets_path} に設定してください。"
        )
    return resolved


def build_service(credentials_values: dict[str, str]):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    credentials = Credentials(
        token=None,
        refresh_token=credentials_values["FORMS_OAUTH_REFRESH_TOKEN"],
        client_id=credentials_values["FORMS_OAUTH_CLIENT_ID"],
        client_secret=credentials_values["FORMS_OAUTH_CLIENT_SECRET"],
        token_uri=_TOKEN_URI,
        scopes=list(_SCOPES),
    )
    credentials.refresh(Request())
    return build("forms", "v1", credentials=credentials, cache_discovery=False)
