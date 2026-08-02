"""YouTube Data API v3 OAuth. Mirrors _drive_common.py's pattern (see that file
for why: same shape, separate credentials since the scope is different and
narrower — no reason for the YouTube app to hold Drive-wide access, or vice versa).
"""
from __future__ import annotations

import os
from pathlib import Path

_LOCAL_SECRETS_FALLBACK = Path.home() / ".academic-audio" / "youtube-secrets.env"
# youtube.upload だけでは再生リストへの追加ができないため、管理スコープを使う。
_SCOPES = ("https://www.googleapis.com/auth/youtube",)
_TOKEN_URI = "https://oauth2.googleapis.com/token"
_REQUIRED_VARS = (
    "YOUTUBE_OAUTH_CLIENT_ID",
    "YOUTUBE_OAUTH_CLIENT_SECRET",
    "YOUTUBE_OAUTH_REFRESH_TOKEN",
)


class YouTubeConfigError(Exception):
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
        raise YouTubeConfigError(
            "YouTube 認証情報が不足しています: "
            f"{', '.join(missing)}。scripts/authorize_youtube.py で取得し、環境変数か "
            f"{local_secrets_path} に設定してください。"
        )
    return resolved


def build_service(credentials_values: dict[str, str]):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    credentials = Credentials(
        token=None,
        refresh_token=credentials_values["YOUTUBE_OAUTH_REFRESH_TOKEN"],
        client_id=credentials_values["YOUTUBE_OAUTH_CLIENT_ID"],
        client_secret=credentials_values["YOUTUBE_OAUTH_CLIENT_SECRET"],
        token_uri=_TOKEN_URI,
        scopes=list(_SCOPES),
    )
    credentials.refresh(Request())
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)
