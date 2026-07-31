#!/usr/bin/env python3
"""Render text to WAV with macOS `say` and `afconvert`.

This is a local adapter that can be passed to Academic Audio as a command
template when Piper is not installed:

  --piper-command "python3 scripts/macos_say_tts.py --output {out} --text {text}"
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--voice", default="Samantha")
    parser.add_argument("--sample-rate", type=int, default=22050)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        aiff = Path(directory) / "speech.aiff"
        subprocess.run(["say", "-v", args.voice, "-o", str(aiff), args.text], check=True)
        subprocess.run(
            [
                "afconvert",
                str(aiff),
                str(args.output),
                "-f",
                "WAVE",
                "-d",
                f"LEI16@{args.sample_rate}",
            ],
            check=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
