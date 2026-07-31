#!/usr/bin/env python3
"""Academic Audio CLI.

Examples:
  python3 scripts/academic_audio_cli.py doctor --json
  python3 scripts/academic_audio_cli.py script generate --review-id dsa.ch02.list.s01 --repo-root ../DSA
  python3 scripts/academic_audio_cli.py generate --source notes.md --engine wav
  python3 scripts/academic_audio_cli.py job status <job-id>
  python3 scripts/academic_audio_cli.py job resume <job-id>
  python3 scripts/academic_audio_cli.py listening generate --source english.md --speeds 0.8,1.0,1.2
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from academic_audio.engines import (  # noqa: E402
    PiperEngine,
    StyleBertVITS2Engine,
    TTSEngineError,
    WavEngine,
    select_engine,
)
from academic_audio.jobs import default_state_dir, job_path, new_job_id, read_job, read_script, write_job  # noqa: E402
from academic_audio.listening import create_listening_script  # noqa: E402
from academic_audio.models import AudioJob  # noqa: E402
from academic_audio.planner import create_dialogue  # noqa: E402
from academic_audio.renderer import render_script  # noqa: E402
from academic_audio.source import AudioSourceError, resolve_source  # noqa: E402


def _source_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--review-id")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--course")


def _engine_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--engine", choices=["auto", "piper", "style-bert-vits2", "wav"], default="auto")
    parser.add_argument("--mode", choices=["fast", "balanced", "quality"], default="balanced")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--piper-command", help="Command template; supports {text}, {out}, {speaker}, {speed}, {language}")
    parser.add_argument("--style-bert-command", help="Command template; supports {text}, {out}, {speaker}, {speed}, {language}")
    parser.add_argument("--style-bert-endpoint", help="HTTP endpoint that returns WAV bytes")


def _state_dir(args: argparse.Namespace) -> Path:
    return args.state_dir or default_state_dir()


def _cmd_doctor(args: argparse.Namespace) -> int:
    engines = [
        PiperEngine(args.piper_command),
        StyleBertVITS2Engine(args.style_bert_command, args.style_bert_endpoint),
        WavEngine(),
    ]
    payload = {
        "state_dir": str(_state_dir(args)),
        "engines": {engine.name: {"available": engine.available()[0], "reason": engine.available()[1]} for engine in engines},
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for name, result in payload["engines"].items():
            mark = "ok" if result["available"] else "missing"
            print(f"{name}: {mark} ({result['reason']})")
    return 0


def _plan_script(args: argparse.Namespace):
    source = resolve_source(
        review_id=args.review_id,
        source_path=args.source,
        repo_root=args.repo_root,
        course=args.course,
    )
    return create_dialogue(source, speed=args.speed)


def _cmd_script_generate(args: argparse.Namespace) -> int:
    script = _plan_script(args)
    out_dir = args.out_dir or (_state_dir(args) / "scripts" / new_job_id(script.source_id))
    json_path, md_path = script.write(out_dir)
    print(json.dumps({"dialogue_json": str(json_path), "dialogue_md": str(md_path)}, ensure_ascii=False, indent=2))
    return 0


def _render_job(job: AudioJob, args: argparse.Namespace, *, force: bool = False) -> AudioJob:
    script = read_script(Path(job.script_path))
    engine = select_engine(
        job.engine,  # type: ignore[arg-type]
        job.mode,  # type: ignore[arg-type]
        piper_command=args.piper_command,
        style_bert_command=args.style_bert_command,
        style_bert_endpoint=args.style_bert_endpoint,
    )
    ok, reason = engine.available()
    if not ok:
        raise TTSEngineError(reason)
    job.status = "rendering"
    write_job(job)
    rendered, failed, output = render_script(
        script,
        engine,
        job_dir=Path(job.job_dir),
        cache_dir=_state_dir(args) / "cache",
        force=force,
    )
    job.rendered_segments = rendered
    job.failed_segments = failed
    job.output_path = str(output)
    job.status = "failed" if failed else "completed"
    job.error = f"failed segments: {', '.join(failed)}" if failed else None
    write_job(job)
    return job


def _cmd_generate(args: argparse.Namespace) -> int:
    script = _plan_script(args)
    job_id = args.job_id or new_job_id(script.source_id)
    directory = args.out_dir or job_path(_state_dir(args), job_id)
    script_path, _ = script.write(directory)
    job = AudioJob(
        job_id=job_id,
        status="planned",
        engine=args.engine,
        mode=args.mode,
        speed=args.speed,
        job_dir=str(directory),
        script_path=str(script_path),
    )
    write_job(job)
    job = _render_job(job, args, force=args.force)
    print(json.dumps(job.to_json_dict(), ensure_ascii=False, indent=2))
    return 0 if job.status == "completed" else 2


def _cmd_job_status(args: argparse.Namespace) -> int:
    job = read_job(_state_dir(args), args.job_id)
    print(json.dumps(job.to_json_dict(), ensure_ascii=False, indent=2))
    return 0 if job.status != "failed" else 2


def _cmd_job_resume(args: argparse.Namespace) -> int:
    job = read_job(_state_dir(args), args.job_id)
    job = _render_job(job, args, force=False)
    print(json.dumps(job.to_json_dict(), ensure_ascii=False, indent=2))
    return 0 if job.status == "completed" else 2


def _cmd_listening_generate(args: argparse.Namespace) -> int:
    source = resolve_source(review_id=args.review_id, source_path=args.source, repo_root=args.repo_root, course=args.course)
    outputs = []
    for speed in [float(item.strip()) for item in args.speeds.split(",") if item.strip()]:
        script = create_listening_script(source, mode=args.listening_mode, speed=speed, limit=args.limit)
        job_id = new_job_id(f"{script.source_id}-{args.listening_mode}-{speed:g}")
        directory = (args.out_dir or job_path(_state_dir(args), job_id))
        script_path, _ = script.write(directory)
        job = AudioJob(
            job_id=job_id,
            status="planned",
            engine=args.engine,
            mode=args.mode,
            speed=speed,
            job_dir=str(directory),
            script_path=str(script_path),
        )
        write_job(job)
        outputs.append(_render_job(job, args, force=args.force).to_json_dict())
    print(json.dumps({"jobs": outputs}, ensure_ascii=False, indent=2))
    return 0 if all(job["status"] == "completed" for job in outputs) else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state-dir", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="TTS環境と出力状態を診断する")
    _engine_args(doctor)
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=_cmd_doctor)

    script_parser = subparsers.add_parser("script", help="台本操作")
    script_sub = script_parser.add_subparsers(dest="script_command", required=True)
    script_generate = script_sub.add_parser("generate", help="対話台本を生成する")
    _source_args(script_generate)
    script_generate.add_argument("--speed", type=float, default=1.0)
    script_generate.add_argument("--out-dir", type=Path)
    script_generate.set_defaults(func=_cmd_script_generate)

    generate = subparsers.add_parser("generate", help="台本生成から音声出力まで実行する")
    _source_args(generate)
    _engine_args(generate)
    generate.add_argument("--out-dir", type=Path)
    generate.add_argument("--job-id")
    generate.add_argument("--force", action="store_true")
    generate.set_defaults(func=_cmd_generate)

    job = subparsers.add_parser("job", help="ジョブ操作")
    job_sub = job.add_subparsers(dest="job_command", required=True)
    status = job_sub.add_parser("status", help="ジョブ状態を表示する")
    status.add_argument("job_id")
    status.set_defaults(func=_cmd_job_status)
    resume = job_sub.add_parser("resume", help="失敗または中断したジョブを再開する")
    resume.add_argument("job_id")
    _engine_args(resume)
    resume.add_argument("--force", action="store_true")
    resume.set_defaults(func=_cmd_job_resume)

    listening = subparsers.add_parser("listening", help="リスニング教材生成")
    listening_sub = listening.add_subparsers(dest="listening_command", required=True)
    listening_generate = listening_sub.add_parser("generate", help="文単位のリスニング音声を生成する")
    _source_args(listening_generate)
    _engine_args(listening_generate)
    listening_generate.add_argument("--listening-mode", choices=["sentence", "shadowing", "dictation"], default="sentence")
    listening_generate.add_argument("--speeds", default="1.0")
    listening_generate.add_argument("--limit", type=int, default=20)
    listening_generate.add_argument("--out-dir", type=Path)
    listening_generate.add_argument("--force", action="store_true")
    listening_generate.set_defaults(func=_cmd_listening_generate)

    args = parser.parse_args()
    try:
        return args.func(args)
    except (AudioSourceError, TTSEngineError, FileNotFoundError, json.JSONDecodeError, ValueError) as error:
        if getattr(args, "json", False):
            print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        else:
            print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
