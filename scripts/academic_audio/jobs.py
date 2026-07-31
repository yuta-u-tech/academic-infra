"""Persistent local job management for Academic Audio."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .models import AudioJob, DialogueScript


def default_state_dir() -> Path:
    return Path.cwd() / ".academic-audio"


def new_job_id(source_id: str) -> str:
    safe = "".join(char if char.isalnum() or char in ".-" else "-" for char in source_id).strip("-")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{safe or 'audio'}"


def job_path(state_dir: Path, job_id: str) -> Path:
    return state_dir / "jobs" / job_id


def write_job(job: AudioJob) -> Path:
    path = Path(job.job_dir) / "job.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(job.to_json_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def read_job(state_dir: Path, job_id: str) -> AudioJob:
    return AudioJob.from_json_dict(json.loads((job_path(state_dir, job_id) / "job.json").read_text(encoding="utf-8")))


def read_script(path: Path) -> DialogueScript:
    return DialogueScript.from_json_dict(json.loads(path.read_text(encoding="utf-8")))
