"""TOEIC Part1（写真描写）用の画像生成。

現在のバックエンドはCodex(内部でOpenAIの画像生成ツールを呼ぶ、`~/.codex/generated_images/`に
既に生成実績あり・追加のAPIキー発行不要)。将来ローカル生成(mflux+FLUX等)に差し替える
可能性がある（2026-08-14、ユーザーと合意した段階的移行方針）ため、バックエンド呼び出しを
`generate_image()` の1関数に閉じ込めてある。差し替え時はこの関数の中身だけ変えればよい。

Codexが生成した画像は使い捨てにせず、`archive_to_corpus()` で永続コーパスへコピーする
（将来のローカルモデルLoRAファインチューニングの教師データにするため）。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CORPUS_DIR = Path.home() / "academic-english-data" / "part1-image-corpus"
_PUBLIC_FOLDER_PATH = ("TOEIC", "listening", "part1-images")


def generate_image(prompt: str, out_path: Path, *, timeout: int = 300) -> Path:
    """promptの画像を生成しout_pathに保存する。

    完了までこの呼び出しをブロックする（Codexの画像生成ツール呼び出し自体が数十秒〜
    かかるため）。呼び出し側がバックグラウンド化したい場合は、この関数を呼ぶプロセス
    自体をBashツールの`run_in_background`で非同期化すること（agentのメッセージング経由の
    非同期回収は2026-08-14に実際に機能しなかった実績があるため使わない）。
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    codex_prompt = (
        f"{prompt} Save the generated image as {out_path.name} in the current working directory."
    )
    subprocess.run(
        [
            "codex", "exec",
            "-s", "workspace-write",
            "-C", str(out_path.parent),
            "--skip-git-repo-check",
            codex_prompt,
        ],
        stdin=subprocess.DEVNULL,
        check=True,
        timeout=timeout,
    )
    if not out_path.exists():
        raise RuntimeError(f"Codexが画像を生成しませんでした（期待した出力先: {out_path}）。")
    return out_path


def archive_to_corpus(image_path: Path, review_id: str) -> Path:
    """将来のローカルモデル(mflux)LoRA学習データとして永続保存する（削除しない）。"""
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    dest = CORPUS_DIR / f"{review_id}.png"
    dest.write_bytes(image_path.read_bytes())
    return dest


def publish_to_drive(image_path: Path, review_id: str) -> dict[str, str]:
    """Google FormsのquestionItem.imageに表示するため、Driveへアップロードし
    直接アクセス可能なURLを返す。

    アップロード先は`TOEIC/listening/part1-images/`専用フォルダに限定し、
    このフォルダにだけ`grant_anyone_reader()`（リンクを知っている全員が閲覧可）を
    かける（2026-08-14、ユーザー承認済みの例外運用。他のDriveフォルダはこれまで通り
    許可アカウント限定のまま）。ファイル名は`{review_id}.png`で固定するので、
    同じreview_idで再アップロードしても同一ファイルを上書きするだけで増殖しない。
    """
    import _drive_common

    credentials = _drive_common.resolve_credentials()
    parent_id = credentials["GDRIVE_PARENT_FOLDER_ID"]
    service = _drive_common.build_service(credentials)

    folder_id = parent_id
    for name in _PUBLIC_FOLDER_PATH:
        folder_id = _drive_common.ensure_folder(service, folder_id, name)
    _drive_common.grant_anyone_reader(service, folder_id)

    file_id = _drive_common.upload_file(service, folder_id, image_path, "image/png", name=f"{review_id}.png")
    return {
        "file_id": file_id,
        "url": f"https://drive.google.com/uc?export=view&id={file_id}",
    }
