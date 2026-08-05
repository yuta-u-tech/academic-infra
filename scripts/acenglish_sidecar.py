#!/usr/bin/env python3
"""Tauri sidecar 用エントリポイント。PyInstaller でこれを単一バイナリ化し、
desktop/src-tauri がプロセスとして spawn する。

`acenglish_cli.py serve` と等価だが、CLI引数解析を経由せず直接
127.0.0.1 に固定して起動する（ensure_loopback() の制約はそのまま有効）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acenglish.api import DEFAULT_HOST, DEFAULT_PORT, run  # noqa: E402

if __name__ == "__main__":
    run(DEFAULT_HOST, DEFAULT_PORT)
