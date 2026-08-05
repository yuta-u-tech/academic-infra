#!/usr/bin/env bash
# Builds the FastAPI backend into a single-file PyInstaller binary and
# places it in src-tauri/binaries/ with the target-triple suffix Tauri's
# externalBin loader requires. Run from anywhere; paths are resolved
# relative to this script.
set -euo pipefail

DESKTOP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$DESKTOP_DIR/.." && pwd)"
DIST_DIR="$REPO_ROOT/dist"
BUILD_DIR="$REPO_ROOT/build"
BINARIES_DIR="$DESKTOP_DIR/src-tauri/binaries"

TARGET_TRIPLE="$(rustc -Vv | awk '/^host:/ { print $2 }')"
if [ -z "$TARGET_TRIPLE" ]; then
  echo "error: could not determine target triple via 'rustc -Vv'" >&2
  exit 1
fi

cd "$REPO_ROOT"
python3 -m PyInstaller --noconfirm --clean scripts/acenglish/sidecar.spec

mkdir -p "$BINARIES_DIR"
cp "$DIST_DIR/acenglish-server" "$BINARIES_DIR/acenglish-server-$TARGET_TRIPLE"
chmod +x "$BINARIES_DIR/acenglish-server-$TARGET_TRIPLE"

rm -rf "$DIST_DIR" "$BUILD_DIR"

echo "sidecar built: $BINARIES_DIR/acenglish-server-$TARGET_TRIPLE"
