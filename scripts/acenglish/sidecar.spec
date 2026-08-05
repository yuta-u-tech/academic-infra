# PyInstaller spec for the Tauri sidecar. Build from academic-infra/ root:
#   pyinstaller scripts/acenglish/sidecar.spec
# Output: dist/acenglish-server (single-file binary), then desktop/build-sidecar.sh
# renames/copies it into desktop/src-tauri/binaries/ with the target-triple suffix
# Tauri's externalBin loader expects.
from pathlib import Path

block_cipher = None
repo_root = Path(SPECPATH).resolve().parent.parent

a = Analysis(
    [str(repo_root / "scripts" / "acenglish_sidecar.py")],
    pathex=[str(repo_root / "scripts")],
    datas=[(str(repo_root / "web"), "web")],
    hiddenimports=["uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto"],
    hookspath=[],
    runtime_hooks=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="acenglish-server",
    console=True,
    onefile=True,
)
