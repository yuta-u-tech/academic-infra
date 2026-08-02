#!/usr/bin/env python3
"""Academic Audio CLI.

Examples:
  python3 scripts/academic_audio_cli.py doctor --json
  python3 scripts/academic_audio_cli.py script generate --review-id dsa.ch02.list.s01 --repo-root ../DSA
  python3 scripts/academic_audio_cli.py generate --source notes.md --engine wav
  python3 scripts/academic_audio_cli.py render --script dialogue.json --engine wav
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

from _data_repo import DataRepoError, commit_and_push, data_repo_path  # noqa: E402
from academic_audio.engines import (  # noqa: E402
    PiperEngine,
    StyleBertVITS2Engine,
    TTSEngineError,
    WavEngine,
    select_engine,
)
from academic_audio.artifact import build_artifact, write_artifact  # noqa: E402
from academic_audio.formats import FormatError, available_formats, load_format  # noqa: E402
from academic_audio.items import ItemValidationError, load_result, to_answers, to_script  # noqa: E402
from academic_audio.jobs import default_state_dir, job_path, new_job_id, read_job, read_script, write_job  # noqa: E402
from academic_audio.listening import create_listening_script  # noqa: E402
from academic_audio.models import AudioJob  # noqa: E402
from academic_audio.planner import create_dialogue  # noqa: E402
from academic_audio.renderer import render_script  # noqa: E402
from academic_audio.source import AudioSourceError, resolve_source  # noqa: E402
from academic_audio import vocab  # noqa: E402
from academic_audio.vocab import VocabFetchError  # noqa: E402
from academic_audio.worksheet import WorksheetError, build_pdf, render_tex  # noqa: E402


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
    parser.add_argument("--piper-model", help="Path to a Piper voice model (.onnx). Required for the default piper invocation")
    parser.add_argument("--style-bert-command", help="Command template; supports {text}, {out}, {speaker}, {speed}, {language}")
    parser.add_argument("--style-bert-endpoint", help="HTTP endpoint that returns WAV bytes")


def _state_dir(args: argparse.Namespace) -> Path:
    return args.state_dir or default_state_dir()


def _cmd_doctor(args: argparse.Namespace) -> int:
    engines = [
        PiperEngine(args.piper_command, args.piper_model),
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
        piper_model=args.piper_model,
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
    if rendered and output.exists():
        # Publisher (Issue #3) への受け渡し。タイムライン・hash・チャプターを添える。
        write_artifact(
            build_artifact(
                job=job,
                script=script,
                script_path=Path(job.script_path),
                audio_path=output,
                rendered=rendered,
            ),
            Path(job.job_dir),
        )
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


PROMPT_VERSION = "2026-08-02.1"
# 科目フォルダの下ではなく、Academic Materials 直下の独立フォルダに出す。
DEFAULT_DRIVE_FOLDER_NAME = "英語リスニング"


def _cmd_listening_publish(args: argparse.Namespace) -> int:
    """Upload the worksheet PDF to Drive, in its own space — not nested under a course.

    リスニング教材は特定の科目に従属しない（内容がある科目のセクションに由来していても、
    英語運用の練習という別の科目である）。academic-english-data がコンテンツの正本を
    持つのに合わせて、Drive 側も科目フォルダとは別の場所へ出す。
    音声そのものは容量が大きいので上げない。配信は Issue #3 の Publisher が担う。
    """
    import _drive_common

    worksheet = args.set_dir / "worksheet.pdf"
    if not worksheet.exists():
        raise FileNotFoundError(f"{worksheet} がありません。先に listening ingest を実行してください。")

    answers_path = args.set_dir / "answers.json"
    format_id = None
    if answers_path.exists():
        format_id = json.loads(answers_path.read_text(encoding="utf-8")).get("format")

    drive_name = args.name or f"{args.set_dir.name}.pdf"
    folder_names = [args.folder_name, *([format_id] if format_id else [])]
    drive_path = "/".join([*folder_names, drive_name])

    if args.dry_run:
        # 認証情報が無くても投稿先は確認できるべきなので、ここでは要求しない。
        print(json.dumps({"dry_run": True, "drive_path": drive_path, "local": str(worksheet)}, ensure_ascii=False, indent=2))
        return 0

    credentials = _drive_common.resolve_credentials()
    parent_id = args.parent_id or credentials.get("GDRIVE_PARENT_FOLDER_ID", "")
    if not parent_id:
        raise ValueError("--parent-id か GDRIVE_PARENT_FOLDER_ID が必要です。")

    service = _drive_common.build_service(credentials)
    folder_id = parent_id
    for name in folder_names:
        folder_id = _drive_common.ensure_folder(service, folder_id, name)
    file_id = _drive_common.upload_file(service, folder_id, worksheet, "application/pdf", name=drive_name)
    print(json.dumps(
        {"drive_path": drive_path, "file_id": file_id, "url": f"https://drive.google.com/file/d/{file_id}/view"},
        ensure_ascii=False, indent=2))
    return 0


def _cmd_listening_request(args: argparse.Namespace) -> int:
    """Emit the request Claude answers. 件数と形式は呼び出し側が決めて渡す。"""
    listening_format = load_format(args.format)
    source = resolve_source(
        review_id=args.review_id, source_path=args.source, repo_root=args.repo_root, course=args.course
    )
    payload = {
        "schema_version": 1,
        "prompt_version": PROMPT_VERSION,
        "instructions": [
            "audio/prompts/listening.md の共通方針に従う",
            f"{listening_format.path.relative_to(Path.cwd()) if listening_format.path.is_relative_to(Path.cwd()) else listening_format.path} の作問方針に従う",
            f"{args.count} 問を items 配列として書く。足りなければ減らしてよい",
        ],
        "format": {
            "id": listening_format.id,
            "name": listening_format.name,
            "language": listening_format.language,
            "answer_in_audio": listening_format.answer_in_audio,
            "item": [
                {"role": slot.role, "count": slot.count, "words": list(slot.words) if slot.words else None}
                for slot in listening_format.item
            ],
        },
        "count": args.count,
        "target": {
            "source_id": source.source_id,
            "review_id": source.review_id,
            "course_id": source.course_id,
            "title": source.title,
            "source_commit": source.source_commit,
        },
        "material": source.body,
    }
    if args.vocab_deck:
        terms = vocab.sample_terms(args.vocab_deck, args.vocab_count)
        payload["vocabulary"] = {"source": vocab.REPOSITORY, "deck": args.vocab_deck, "terms": terms}
        payload["instructions"].append(
            f"vocabulary（{args.vocab_deck} から{len(terms)}語）のうち、資料の話題に馴染むものだけを"
            "質問文か応答のどこかで自然に使う。無理に全語を使わない。使った語は reason に書く"
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"request": str(args.out), "format": listening_format.id, "count": args.count}, ensure_ascii=False, indent=2))
    return 0


def _cmd_listening_ingest(args: argparse.Namespace) -> int:
    """Validate Claude's items, then derive the script, the answer key and the worksheet.

    出力先の既定は academic-english-data（正本）。科目リポジトリが TeX ソースの正本を
    持つのと同じ形で、生成した教材のソース（台本・解答・.tex）はそこに置く。
    """
    listening_format = load_format(args.format)
    listening_set = load_result(args.file, listening_format)
    script = to_script(listening_set, listening_format)

    slug = new_job_id(f"{listening_set.source_id}-{listening_format.id}")
    out_dir = args.out_dir or (data_repo_path() / "listening" / slug)
    out_dir.mkdir(parents=True, exist_ok=True)
    script_path, script_md = script.write(out_dir)
    answers_path = out_dir / "answers.json"
    answers_path.write_text(
        json.dumps(to_answers(listening_set), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    tex_path = out_dir / "worksheet.tex"
    tex_path.write_text(render_tex(listening_set, listening_format), encoding="utf-8")

    result = {
        "items": len(listening_set.items),
        "segments": len(script.segments),
        "dialogue_json": str(script_path),
        "dialogue_md": str(script_md),
        "answers_json": str(answers_path),
        "worksheet_tex": str(tex_path),
    }
    if not args.no_pdf:
        # PDF は academic-english-data の .gitignore で除外している。正本は .tex から再現できる形。
        result["worksheet_pdf"] = str(build_pdf(tex_path))
    if args.push:
        try:
            pushed = commit_and_push(
                data_repo_path(), [script_path, script_md, answers_path, tex_path], f"listening: {slug}"
            )
        except DataRepoError as error:
            print(f"push できませんでした: {error}", file=sys.stderr)
            return 1
        result["pushed"] = pushed
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    """Render a dialogue.json that was written outside the deterministic planner.

    `audio/prompts/*.md` に従って書いた台本を、そのまま音声にするための入口。
    """
    script = read_script(args.script)
    job_id = args.job_id or new_job_id(script.source_id)
    directory = args.out_dir or job_path(_state_dir(args), job_id)
    # 台本をジョブ配下へ写しておく。job resume が同じ台本を読めるようにするため。
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

    render = subparsers.add_parser("render", help="既存の台本ファイルから音声を生成する")
    render.add_argument("--script", type=Path, required=True, help="dialogue.json のパス")
    _engine_args(render)
    render.add_argument("--out-dir", type=Path)
    render.add_argument("--job-id")
    render.add_argument("--force", action="store_true")
    render.set_defaults(func=_cmd_render)

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

    listening_request = listening_sub.add_parser("request", help="作問の依頼JSONを書き出す")
    _source_args(listening_request)
    listening_request.add_argument("--format", required=True, help=f"使えるのは: {', '.join(available_formats())}")
    listening_request.add_argument("--count", type=int, required=True, help="生成する問題数")
    listening_request.add_argument("--out", type=Path, required=True)
    listening_request.add_argument("--vocab-deck", choices=vocab.DECKS, help="study-forge の単語デッキ（金フレ由来）から語彙を混ぜる")
    listening_request.add_argument("--vocab-count", type=int, default=5, help="混ぜる語数")
    listening_request.set_defaults(func=_cmd_listening_request)

    listening_ingest = listening_sub.add_parser("ingest", help="作問結果を検証して台本・解答・問題冊子を出す")
    listening_ingest.add_argument("--file", type=Path, required=True)
    listening_ingest.add_argument("--format", required=True)
    listening_ingest.add_argument("--out-dir", type=Path, help="既定: academic-english-data/listening/<slug>")
    listening_ingest.add_argument("--no-pdf", action="store_true", help="TeX まで出して組版しない")
    listening_ingest.add_argument("--push", action="store_true", help="出力を academic-english-data へ commit + push する")
    listening_ingest.set_defaults(func=_cmd_listening_ingest)

    listening_publish = listening_sub.add_parser("publish", help="問題冊子PDFを Drive の科目フォルダへ上げる")
    listening_publish.add_argument("--set-dir", type=Path, required=True, help="listening ingest の出力先")
    listening_publish.add_argument("--folder-name", default=DEFAULT_DRIVE_FOLDER_NAME, help="Drive 上のトップフォルダ名")
    listening_publish.add_argument("--name", help="Drive 上のファイル名（既定: <set-dir名>.pdf）")
    listening_publish.add_argument("--parent-id", help="Academic Materials のフォルダID")
    listening_publish.add_argument("--dry-run", action="store_true")
    listening_publish.set_defaults(func=_cmd_listening_publish)

    args = parser.parse_args()
    try:
        return args.func(args)
    except (
        AudioSourceError,
        DataRepoError,
        FormatError,
        ItemValidationError,
        TTSEngineError,
        VocabFetchError,
        WorksheetError,
        FileNotFoundError,
        json.JSONDecodeError,
        ValueError,
    ) as error:
        if getattr(args, "json", False):
            print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        else:
            print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
