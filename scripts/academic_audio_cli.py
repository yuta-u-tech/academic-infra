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
  python3 scripts/academic_audio_cli.py youtube publish <job-id> --dry-run
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from dataclasses import asdict
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data_repo import DataRepoError, commit_and_push, data_repo_path  # noqa: E402
from acenglish.db import connect  # noqa: E402
from acenglish.fetch import import_toeic_listening, import_toeic_listening_passage  # noqa: E402
from academic_audio.engines import (  # noqa: E402
    MultiSpeakerPiperEngine,
    PiperEngine,
    StyleBertVITS2Engine,
    TTSEngineError,
    WavEngine,
    parse_speaker_map,
    select_engine,
)
from academic_audio.artifact import build_artifact, read_artifact, write_artifact  # noqa: E402
from academic_audio.formats import FormatError, available_formats, load_format  # noqa: E402
from academic_audio.items import (  # noqa: E402
    ItemValidationError,
    check_answer_distribution,
    load_passage_result,
    load_result,
    passage_to_answers,
    passage_to_form_items,
    passage_to_script,
    to_answers,
    to_form_items,
    to_script,
)
from academic_audio.jobs import default_state_dir, job_path, new_job_id, read_job, read_script, write_job  # noqa: E402
from academic_audio.listening import create_listening_script  # noqa: E402
from academic_audio.metadata import describe as describe_video_metadata  # noqa: E402
from academic_audio.models import AudioJob  # noqa: E402
from academic_audio import part1_images  # noqa: E402
from academic_audio.planner import create_dialogue  # noqa: E402
from academic_audio.publications import read_publication  # noqa: E402
from academic_audio.publisher import DEFAULT_VISIBILITY, LocalPublisher, PublishError, YouTubePublisher  # noqa: E402
from academic_audio.renderer import render_script  # noqa: E402
from academic_audio.review_script import ReviewItemError, build_review_script  # noqa: E402
from academic_audio.source import AudioSourceError, resolve_source  # noqa: E402
from academic_audio import vocab  # noqa: E402
from academic_audio.vocab import VocabFetchError  # noqa: E402
from academic_audio.video import VideoError  # noqa: E402
from academic_audio.worksheet import WorksheetError, build_pdf, render_passage_tex, render_tex  # noqa: E402
from _youtube_common import YouTubeConfigError, resolve_credentials as resolve_youtube_credentials  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")


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
    parser.add_argument(
        "--piper-voice-map",
        help='話者ごとに別の Piper 音声モデルを使う（会話形式向け）。例: "A=<voice1.onnx>,B=<voice2.onnx>,narrator=<voice1.onnx>"。'
        "指定すると --engine / --mode より優先される",
    )


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
    voice_map_raw = getattr(args, "piper_voice_map", None)
    if voice_map_raw:
        engine = MultiSpeakerPiperEngine(parse_speaker_map(voice_map_raw))
    else:
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


PROMPT_VERSION = "2026-08-02.2"
# 科目フォルダの下ではなく、Academic Materials 直下の固定フォルダに出す。
# 毎回同じ場所に格納されることを優先し、形式(Part2/3/4)ではフォルダを分けない。
DEFAULT_DRIVE_FOLDER_NAME = "TOEIC/listening"
# new_job_id() が付ける生成時刻の接頭辞（例: 20260802T072921Z-）。Drive 上のファイル名は
# 投稿日を先頭に付けるので、ここに元々ある時刻と二重にならないよう剥がす。
_JOB_TIMESTAMP_PREFIX = re.compile(r"^\d{8}T\d{6}Z-")


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

    # 日次更新を想定し、投稿日を先頭に付ける。同じ set-dir を別日に publish しても
    # 上書きにならず、Drive 上で「いつの分か」が一目でわかる。
    today = datetime.now(JST).strftime("%Y-%m-%d")
    descriptive_name = _JOB_TIMESTAMP_PREFIX.sub("", args.set_dir.name)
    folder_names = [part for part in args.folder_name.split("/") if part]
    # TOEIC は Part ごとにサブフォルダへ分ける（Part2/3/4 が同じ場所に混ざると探しにくいため）。
    part_match = re.match(r"toeic-(part\d+)$", descriptive_name)
    if part_match:
        folder_names.append(part_match.group(1))
        drive_name = args.name or f"{today}.pdf"
    else:
        drive_name = args.name or f"{today}-{descriptive_name}.pdf"
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


def _build_publisher(args: argparse.Namespace):
    if args.local:
        return LocalPublisher(state_dir=_state_dir(args))
    credentials = resolve_youtube_credentials()
    return YouTubePublisher(
        state_dir=_state_dir(args), credentials=credentials, visibility=args.visibility, playlist_id=args.playlist_id
    )


def _cmd_youtube_doctor(args: argparse.Namespace) -> int:
    publisher = _build_publisher(args)
    publisher.health_check()
    print(json.dumps({"ok": True, "publisher": "local" if args.local else "youtube"}, ensure_ascii=False, indent=2))
    return 0


def _cmd_youtube_publish(args: argparse.Namespace) -> int:
    """Turn a rendered job's audio into an MP4 and publish it (既定は限定公開)。

    重複投稿防止: 同じ audio_hash が既に uploaded なら再アップロードしない（--force で上書き）。
    """
    job_dir = job_path(_state_dir(args), args.job_id)
    artifact = read_artifact(job_dir)
    publisher = _build_publisher(args)

    if args.dry_run:
        metadata = describe_video_metadata(artifact)
        result = publisher.publish(artifact, dry_run=True)
        print(json.dumps(
            {**asdict(result), "preview": asdict(metadata), "duration": artifact.duration, "chapters": len(artifact.chapters)},
            ensure_ascii=False, indent=2,
        ))
        return 0

    try:
        result = publisher.publish(artifact, force=args.force, keep_video=args.keep_video)
    except PublishError as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.status in ("uploaded", "duplicate") else 1


def _cmd_youtube_status(args: argparse.Namespace) -> int:
    record = read_publication(_state_dir(args), args.publication_id)
    payload = {"publication_id": record.publication_id, "status": record.status, "video_id": record.video_id, "url": record.url, "error": record.error}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if record.status != "failed" else 2


def _cmd_youtube_resume(args: argparse.Namespace) -> int:
    credentials = resolve_youtube_credentials()
    publisher = YouTubePublisher(state_dir=_state_dir(args), credentials=credentials)
    try:
        result = publisher.resume(args.publication_id, keep_video=args.keep_video)
    except PublishError as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.status in ("uploaded", "duplicate") else 1


def _cmd_listening_request(args: argparse.Namespace) -> int:
    """Emit the request Claude answers. 件数と形式は呼び出し側が決めて渡す。"""
    listening_format = load_format(args.format)
    source = resolve_source(
        review_id=args.review_id, source_path=args.source, repo_root=args.repo_root, course=args.course
    )
    format_payload = {
        "id": listening_format.id,
        "name": listening_format.name,
        "language": listening_format.language,
        "answer_in_audio": listening_format.answer_in_audio,
        "grouping": listening_format.grouping,
    }
    is_toeic = listening_format.id.startswith("toeic-part")
    instructions = [
        f"{listening_format.path.relative_to(Path.cwd()) if listening_format.path.is_relative_to(Path.cwd()) else listening_format.path} の作問方針に従う",
    ]
    if is_toeic:
        # TOEIC は特定分野の専門知識を前提にしない試験なので、資料の分野に題材を
        # 縛る audio/prompts/listening.md の共通方針(資料の中心概念から文を選ぶ、等)は
        # 適用しない。代わりに TOEIC 実際の頻出シナリオから題材を選ばせる。
        instructions.append("audio/prompts/toeic-topics.md のシナリオ分類から題材を選ぶ。資料の分野に話題を縛らない")
    else:
        instructions.insert(0, "audio/prompts/listening.md の共通方針に従う")
    if listening_format.grouping == "flat":
        format_payload["item"] = [
            {"role": slot.role, "count": slot.count, "words": list(slot.words) if slot.words else None}
            for slot in listening_format.item
        ]
        instructions.append(f"{args.count} 問を items 配列として書く。足りなければ減らしてよい")
    else:
        assert listening_format.passage_slot is not None and listening_format.question_slot is not None
        format_payload["passage"] = {
            "speakers": listening_format.passage_slot.speakers,
            "turns": list(listening_format.passage_slot.turns),
            "words_per_turn": list(listening_format.passage_slot.words_per_turn),
        }
        format_payload["questions"] = {
            "count": listening_format.question_slot.count,
            "words": list(listening_format.question_slot.words),
            "choice_count": listening_format.question_slot.choice_count,
            "choice_words": list(listening_format.question_slot.choice_words),
        }
        instructions.append(
            f"{args.count} 組を items 配列として書く。各 item は passage（発話配列）と "
            f"{listening_format.question_slot.count} 問の questions を持つ。足りなければ減らしてよい"
        )
    if is_toeic:
        instructions.append(
            "結果 JSON の source_id には review_id ではなく format id "
            f"（\"{listening_format.id}\"）をそのまま書く。YouTube の説明文・タグ・"
            "Driveのファイル名に出るので、資料の科目名を出さないため"
        )
    payload = {
        "schema_version": 1,
        "prompt_version": PROMPT_VERSION,
        "instructions": instructions,
        "format": format_payload,
        "count": args.count,
        "target": {
            # TOEIC は題材を資料から切り離しているので、source_id は format id にする
            # （YouTube description/tags・Drive ファイル名にそのまま出るため）。
            # review_id/course_id は生成の文脈記録として残す。
            "source_id": listening_format.id if is_toeic else source.source_id,
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
        vocab_hint = "選んだシナリオに馴染むものだけを" if is_toeic else "資料の話題に馴染むものだけを"
        payload["instructions"].append(
            f"vocabulary（{args.vocab_deck} から{len(terms)}語）のうち、{vocab_hint}"
            "質問文か応答のどこかで自然に使う。無理に全語を使わない。使った語は reason に書く"
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"request": str(args.out), "format": listening_format.id, "count": args.count}, ensure_ascii=False, indent=2))
    return 0


def _shuffle_flat_item_choices(item: dict) -> None:
    """Part2形式(1問=parts配列)の choice role パートをシャッフルし、answer_index を追従させる。

    音声合成(`items.py: to_script()`)はこの result.json をそのまま読むので、ここで
    シャッフルしておけば音声の読み上げ順と表示順が自動的に一致する
    (2026-08-14、Part5の正解位置がAに92%偏っていた件と同じ作問側の癖への対策)。
    """
    parts = item.get("parts")
    answer_index = item.get("answer_index")
    if not parts or answer_index is None:
        return
    choice_positions = [i for i, part in enumerate(parts) if part.get("role") == "choice"]
    if not choice_positions:
        return
    choice_parts = [parts[i] for i in choice_positions]
    order = list(range(len(choice_parts)))
    random.shuffle(order)
    for position, source_index in zip(choice_positions, order):
        parts[position] = choice_parts[source_index]
    item["answer_index"] = order.index(answer_index)


def _shuffle_passage_item_choices(item: dict) -> None:
    """Part3/4形式(1問=questions配列)の各設問の choices をシャッフルする。"""
    for question in item.get("questions", []):
        choices = question.get("choices")
        answer_index = question.get("answer_index")
        if not choices or answer_index is None:
            continue
        order = list(range(len(choices)))
        random.shuffle(order)
        question["choices"] = [choices[i] for i in order]
        question["answer_index"] = order.index(answer_index)


def _cmd_listening_shuffle_choices(args: argparse.Namespace) -> int:
    listening_format = load_format(args.format)
    payload = json.loads(args.file.read_text(encoding="utf-8"))
    items = payload.get("items")
    if not items:
        raise SystemExit("items がありません。")
    if listening_format.grouping == "passage":
        for item in items:
            _shuffle_passage_item_choices(item)
    else:
        for item in items:
            _shuffle_flat_item_choices(item)
    out_path = args.out or args.file
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"shuffled": len(items), "out": str(out_path)}, ensure_ascii=False, indent=2))
    return 0


def _cmd_listening_ingest(args: argparse.Namespace) -> int:
    """Validate Claude's items, then derive the script, the answer key and the worksheet.

    出力先の既定は academic-english-data（正本）。科目リポジトリが TeX ソースの正本を
    持つのと同じ形で、生成した教材のソース（台本・解答・.tex）はそこに置く。
    """
    listening_format = load_format(args.format)
    if listening_format.grouping == "passage":
        item_set = load_passage_result(args.file, listening_format)
        if not args.allow_skewed_answers:
            check_answer_distribution(
                [question.answer_index for item in item_set.items for question in item.questions]
            )
        script = passage_to_script(item_set, listening_format)
        answers_payload = passage_to_answers(item_set)
        tex = render_passage_tex(item_set, listening_format, youtube_url=args.youtube_url, form_url=args.form_url)
    else:
        item_set = load_result(args.file, listening_format)
        if not args.allow_skewed_answers:
            check_answer_distribution(
                [item.answer_index for item in item_set.items if item.answer_index is not None]
            )
        script = to_script(item_set, listening_format)
        answers_payload = to_answers(item_set)
        tex = render_tex(item_set, listening_format, youtube_url=args.youtube_url, form_url=args.form_url)

    # TOEIC 形式は教材(source_id)の分野と無関係な題材を選ぶので、フォルダ名/Driveの
    # ファイル名に科目名を出さない（出すと「論理回路の問題」に見えて紛らわしい）。
    is_toeic_format = listening_format.id.startswith("toeic-part")
    slug_base = listening_format.id if is_toeic_format else f"{item_set.source_id}-{listening_format.id}"
    slug = new_job_id(slug_base)
    # Part2/3/4 が listening/ 直下に混ざると探しにくいので、Part ごとのサブフォルダへ分ける。
    listening_subdir = listening_format.id.removeprefix("toeic-") if is_toeic_format else None
    out_dir = args.out_dir or (
        data_repo_path() / "listening" / listening_subdir / slug
        if listening_subdir
        else data_repo_path() / "listening" / slug
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    # 元の作問結果もそのまま残す。youtube publish 後に URL を差し込んで
    # worksheet を作り直す（listening attach-youtube-url）ときの再入力になる。
    result_path = out_dir / "result.json"
    result_path.write_text(args.file.read_text(encoding="utf-8"), encoding="utf-8")
    script_path, script_md = script.write(out_dir)
    answers_path = out_dir / "answers.json"
    answers_path.write_text(json.dumps(answers_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tex_path = out_dir / "worksheet.tex"
    tex_path.write_text(tex, encoding="utf-8")
    if args.youtube_url or args.form_url:
        urls = {}
        if args.youtube_url:
            urls["youtube_url"] = args.youtube_url
        if args.form_url:
            urls["form_url"] = args.form_url
        _write_attached_urls(out_dir, urls)

    result = {
        "items": len(item_set.items),
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
                data_repo_path(), [result_path, script_path, script_md, answers_path, tex_path], f"listening: {slug}"
            )
        except DataRepoError as error:
            print(f"push できませんでした: {error}", file=sys.stderr)
            return 1
        result["pushed"] = pushed
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_listening_ingest_db(args: argparse.Namespace) -> int:
    """listening ingest 済みの result.json を学習ループ（english.db）へ取り込む。

    `toeic_reading_cli.py ingest`/`ingest-part7` のリスニング版。既存の `listening ingest`
    は台本・解答・冊子を組むだけで、それ単体では english.db への反映が無かった
    （2026-08-09時点のギャップ）。set-id は review_id に使うので、Form作成
    （`toeic_forms_cli.py create`）で使った review_id と必ず一致させること。
    """
    listening_format = load_format(args.format)
    part = listening_format.id.removeprefix("toeic-")
    with connect(args.db) as connection:
        if listening_format.grouping == "passage":
            item_set = load_passage_result(args.file, listening_format)
            imported = import_toeic_listening_passage(connection, args.set_id, item_set, part)
        else:
            item_set = load_result(args.file, listening_format)
            imported = import_toeic_listening(connection, args.set_id, item_set, part)
    print(
        json.dumps(
            {"set_id": args.set_id, "part": part, "imported": imported}, ensure_ascii=False, indent=2
        )
    )
    return 0


def _cmd_listening_attach_image_urls(args: argparse.Namespace) -> int:
    """result.json内の各itemのimage_path(ローカル写真)をDriveへ公開アップロードし、
    公開URLをimage_urlとして書き戻す(TOEIC Part1専用)。

    forms-items/ingest-db/worksheetのいずれよりも先に実行すること
    （image_urlが無いとForms/PDFに写真が出ない）。review_idの採番規則
    （`toeic.listening.part1.<set-id>.NNNN`）を`to_form_items`と一致させるため、
    `--set-id`は同じ値を渡す。既にimage_urlが付いているitemはスキップする
    （再実行しても同じDriveファイルを上書きするだけで安全だが、通信を省く）。
    """
    payload = json.loads(args.file.read_text(encoding="utf-8"))
    items = payload.get("items")
    if not items:
        raise SystemExit("items がありません。")

    attached = 0
    for index, item in enumerate(items, start=1):
        if item.get("image_url") or not item.get("image_path"):
            continue
        review_id = f"toeic.listening.part1.{args.set_id}.{index:04d}"
        result = part1_images.publish_to_drive(Path(item["image_path"]), review_id)
        item["image_url"] = result["url"]
        attached += 1

    out_path = args.out or args.file
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"attached": attached, "out": str(out_path)}, ensure_ascii=False, indent=2))
    return 0


def _cmd_listening_forms_items(args: argparse.Namespace) -> int:
    """result.json を toeic_forms_cli.py create にそのまま渡せる items.json へ機械的に変換する。

    質問文/選択肢をどう組み立てるかは(review_idの採番規則も含めて)完全に決定論的なので、
    毎回 Claude が手で書くと構成ミス（選択肢テキストの二重表示など）が起きる
    （2026-08-10 に実際に起きた）。この変換はコード側に固定する。
    """
    listening_format = load_format(args.format)
    if listening_format.grouping == "passage":
        item_set = load_passage_result(args.file, listening_format)
        items = passage_to_form_items(item_set, args.set_id)
    else:
        item_set = load_result(args.file, listening_format)
        items = to_form_items(item_set, listening_format, args.set_id)
    payload = {"items": items}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"items": len(items), "out": str(args.out)}, ensure_ascii=False, indent=2))
    return 0


def _read_attached_urls(set_dir: Path) -> dict[str, str]:
    urls_path = set_dir / "urls.json"
    if not urls_path.exists():
        return {}
    return json.loads(urls_path.read_text(encoding="utf-8"))


def _write_attached_urls(set_dir: Path, urls: dict[str, str]) -> None:
    (set_dir / "urls.json").write_text(json.dumps(urls, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _rerender_worksheet_with_urls(set_dir: Path, listening_format, urls: dict[str, str]) -> str:
    """youtube_url と form_url は別々のタイミングで判明するため、両方を urls.json に
    永続化してから常に両方を渡して再描画する。片方だけ渡すと、後から attach した方が
    先に付いていたもう片方のURLを消してしまう。
    """
    result_path = set_dir / "result.json"
    if not result_path.exists():
        raise FileNotFoundError(f"{result_path} がありません。listening ingest の出力先を指定してください。")

    if listening_format.grouping == "passage":
        item_set = load_passage_result(result_path, listening_format)
        return render_passage_tex(
            item_set, listening_format, youtube_url=urls.get("youtube_url"), form_url=urls.get("form_url")
        )
    item_set = load_result(result_path, listening_format)
    return render_tex(
        item_set, listening_format, youtube_url=urls.get("youtube_url"), form_url=urls.get("form_url")
    )


def _cmd_listening_attach_youtube_url(args: argparse.Namespace) -> int:
    """listening ingest 済みの set-dir に、あとから分かる YouTube URL を差し込んで worksheet を作り直す。

    音声(YouTube投稿)は dialogue.json ができてから作るので、冊子は URL を知らない状態で
    先にできている。result.json（元の作問結果）から作り直す。
    """
    listening_format = load_format(args.format)
    urls = _read_attached_urls(args.set_dir)
    urls["youtube_url"] = args.youtube_url
    tex = _rerender_worksheet_with_urls(args.set_dir, listening_format, urls)
    _write_attached_urls(args.set_dir, urls)

    tex_path = args.set_dir / "worksheet.tex"
    tex_path.write_text(tex, encoding="utf-8")

    result = {"worksheet_tex": str(tex_path)}
    if not args.no_pdf:
        result["worksheet_pdf"] = str(build_pdf(tex_path))
    if args.push:
        try:
            pushed = commit_and_push(data_repo_path(), [tex_path], f"listening: attach youtube url ({args.set_dir.name})")
        except DataRepoError as error:
            print(f"push できませんでした: {error}", file=sys.stderr)
            return 1
        result["pushed"] = pushed
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_listening_attach_form_url(args: argparse.Namespace) -> int:
    """listening ingest 済みの set-dir に、Google Form の回答URLを差し込んで worksheet を作り直す。

    `scripts/toeic_forms_cli.py create` で作った Form の responder_url を渡す想定
    （順序: 問題データ生成 → Form作成 → ここでTeXに埋め込み、を厳守）。
    """
    listening_format = load_format(args.format)
    urls = _read_attached_urls(args.set_dir)
    urls["form_url"] = args.form_url
    tex = _rerender_worksheet_with_urls(args.set_dir, listening_format, urls)
    _write_attached_urls(args.set_dir, urls)

    tex_path = args.set_dir / "worksheet.tex"
    tex_path.write_text(tex, encoding="utf-8")

    result = {"worksheet_tex": str(tex_path)}
    if not args.no_pdf:
        result["worksheet_pdf"] = str(build_pdf(tex_path))
    if args.push:
        try:
            pushed = commit_and_push(data_repo_path(), [tex_path], f"listening: attach form url ({args.set_dir.name})")
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


def _cmd_review_script(args: argparse.Namespace) -> int:
    """間違えたTOEIC問題(reason付き)のJSONから復習動画の台本(dialogue.json)を書き出す。

    reasonは`acenglish_cli.py toeic-review`が拾う誤答データに、Claudeが1問ずつ
    短い英語の説明を足したもの。台本の組み立て自体は決定論的（review_script.py）。
    """
    items = json.loads(args.file.read_text(encoding="utf-8"))
    script = build_review_script(args.title, args.source_id, items)
    out_dir = args.out_dir or job_path(_state_dir(args), new_job_id(script.source_id))
    json_path, md_path = script.write(out_dir)
    print(json.dumps({"dialogue_json": str(json_path), "dialogue_md": str(md_path)}, ensure_ascii=False, indent=2))
    return 0


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

    review_script = subparsers.add_parser(
        "review-script", help="間違えたTOEIC問題(reason付きJSON)から復習動画の台本を書く"
    )
    review_script.add_argument("--file", type=Path, required=True, help="[{review_id,sentence,choices,answer_index,reason}] のJSON")
    review_script.add_argument("--title", required=True)
    review_script.add_argument("--source-id", required=True)
    review_script.add_argument("--out-dir", type=Path)
    review_script.set_defaults(func=_cmd_review_script)

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

    listening_shuffle = listening_sub.add_parser(
        "shuffle-choices", help="result.json内の各設問の選択肢順序を機械的にシャッフルする（ingestより前に実行）"
    )
    listening_shuffle.add_argument("--file", type=Path, required=True, help="request の後にClaudeが書いた result.json")
    listening_shuffle.add_argument("--format", required=True)
    listening_shuffle.add_argument("--out", type=Path, help="既定: --file を上書き")
    listening_shuffle.set_defaults(func=_cmd_listening_shuffle_choices)

    listening_ingest = listening_sub.add_parser("ingest", help="作問結果を検証して台本・解答・問題冊子を出す")
    listening_ingest.add_argument("--file", type=Path, required=True)
    listening_ingest.add_argument("--format", required=True)
    listening_ingest.add_argument("--out-dir", type=Path, help="既定: academic-english-data/listening/<slug>")
    listening_ingest.add_argument("--no-pdf", action="store_true", help="TeX まで出して組版しない")
    listening_ingest.add_argument("--push", action="store_true", help="出力を academic-english-data へ commit + push する")
    listening_ingest.add_argument("--youtube-url", help="既に YouTube へ投稿済みの場合、冊子にURLを載せる")
    listening_ingest.add_argument(
        "--form-url", help="既に toeic_forms_cli.py create で回答フォームを作成済みの場合、冊子にURLを載せる"
    )
    listening_ingest.add_argument(
        "--allow-skewed-answers",
        action="store_true",
        help="全問の正解位置が同じでもingestを続行する（本来は shuffle-choices を先に実行すべき、"
        "デバッグ・少数問題セット用の逃げ道）",
    )
    listening_ingest.set_defaults(func=_cmd_listening_ingest)

    listening_ingest_db = listening_sub.add_parser(
        "ingest-db", help="result.json を学習ループ(english.db)へ取り込む"
    )
    listening_ingest_db.add_argument("--file", type=Path, required=True, help="result.json（listening ingestの出力）")
    listening_ingest_db.add_argument("--format", required=True)
    listening_ingest_db.add_argument("--set-id", required=True, help="このセットの識別子（review_idに使う）")
    listening_ingest_db.add_argument("--db", type=Path, help="既定: ~/.academic-english/english.db")
    listening_ingest_db.set_defaults(func=_cmd_listening_ingest_db)

    listening_attach_image_urls = listening_sub.add_parser(
        "attach-image-urls",
        help="result.json内のimage_path(写真)をDriveへ公開アップロードし、image_urlを書き戻す(Part1専用)",
    )
    listening_attach_image_urls.add_argument("--file", type=Path, required=True, help="Claudeが書いたresult.json")
    listening_attach_image_urls.add_argument(
        "--set-id", required=True, help="forms-items/ingest-dbと同じ値(review_idの採番に使う)"
    )
    listening_attach_image_urls.add_argument("--out", type=Path, help="既定: --file を上書き")
    listening_attach_image_urls.set_defaults(func=_cmd_listening_attach_image_urls)

    listening_forms_items = listening_sub.add_parser(
        "forms-items", help="result.json を toeic_forms_cli.py create 用の items.json へ機械的に変換する"
    )
    listening_forms_items.add_argument("--file", type=Path, required=True, help="result.json（作問結果）")
    listening_forms_items.add_argument("--format", required=True)
    listening_forms_items.add_argument("--set-id", required=True, help="review_id に使う識別子（ingest-dbと同じ値にする）")
    listening_forms_items.add_argument("--out", type=Path, required=True)
    listening_forms_items.set_defaults(func=_cmd_listening_forms_items)

    listening_attach_url = listening_sub.add_parser(
        "attach-youtube-url", help="youtube publish で得たURLを冊子に載せて作り直す"
    )
    listening_attach_url.add_argument("--set-dir", type=Path, required=True, help="listening ingest の出力先")
    listening_attach_url.add_argument("--format", required=True)
    listening_attach_url.add_argument("--youtube-url", required=True)
    listening_attach_url.add_argument("--no-pdf", action="store_true")
    listening_attach_url.add_argument("--push", action="store_true", help="更新した worksheet.tex を academic-english-data へ commit + push する")
    listening_attach_url.set_defaults(func=_cmd_listening_attach_youtube_url)

    listening_attach_form_url = listening_sub.add_parser(
        "attach-form-url", help="toeic_forms_cli.py create で得た回答フォームURLを冊子に載せて作り直す"
    )
    listening_attach_form_url.add_argument("--set-dir", type=Path, required=True, help="listening ingest の出力先")
    listening_attach_form_url.add_argument("--format", required=True)
    listening_attach_form_url.add_argument("--form-url", required=True)
    listening_attach_form_url.add_argument("--no-pdf", action="store_true")
    listening_attach_form_url.add_argument(
        "--push", action="store_true", help="更新した worksheet.tex を academic-english-data へ commit + push する"
    )
    listening_attach_form_url.set_defaults(func=_cmd_listening_attach_form_url)

    listening_publish = listening_sub.add_parser("publish", help="問題冊子PDFを Drive の科目フォルダへ上げる")
    listening_publish.add_argument("--set-dir", type=Path, required=True, help="listening ingest の出力先")
    listening_publish.add_argument("--folder-name", default=DEFAULT_DRIVE_FOLDER_NAME, help="Drive 上のフォルダパス（/ 区切りで階層を作る）")
    listening_publish.add_argument("--name", help="Drive 上のファイル名（既定: <当日の日付>-<set-dir名>.pdf）")
    listening_publish.add_argument("--parent-id", help="Academic Materials のフォルダID")
    listening_publish.add_argument("--dry-run", action="store_true")
    listening_publish.set_defaults(func=_cmd_listening_publish)

    youtube = subparsers.add_parser("youtube", help="音声を動画化して YouTube へ投稿する（Issue #3）")
    youtube_sub = youtube.add_subparsers(dest="youtube_command", required=True)

    youtube_doctor = youtube_sub.add_parser("doctor", help="YouTube API に接続できるか確認する")
    youtube_doctor.add_argument("--local", action="store_true", help="YouTube に接続せず LocalPublisher で確認する")
    youtube_doctor.add_argument("--visibility", choices=["unlisted", "private", "public"], default=DEFAULT_VISIBILITY)
    youtube_doctor.add_argument("--playlist-id")
    youtube_doctor.set_defaults(func=_cmd_youtube_doctor)

    youtube_publish = youtube_sub.add_parser("publish", help="ジョブの音声を動画化して投稿する")
    youtube_publish.add_argument("job_id")
    youtube_publish.add_argument("--visibility", choices=["unlisted", "private", "public"], default=DEFAULT_VISIBILITY, help="既定は限定公開")
    youtube_publish.add_argument("--playlist-id", help="投稿後に追加する再生リストID")
    youtube_publish.add_argument("--dry-run", action="store_true", help="動画化・投稿をせず、タイトル/説明文/タグの案だけ見る")
    youtube_publish.add_argument("--force", action="store_true", help="同じ音声が投稿済みでも再投稿する")
    youtube_publish.add_argument("--keep-video", action="store_true", help="投稿後もローカルの動画ファイルを消さない")
    youtube_publish.add_argument("--local", action="store_true", help="YouTube に投稿せず、動画化だけローカルで確認する")
    youtube_publish.set_defaults(func=_cmd_youtube_publish)

    youtube_status = youtube_sub.add_parser("status", help="投稿状態を確認する")
    youtube_status.add_argument("publication_id")
    youtube_status.set_defaults(func=_cmd_youtube_status)

    youtube_resume = youtube_sub.add_parser("resume", help="失敗した投稿をローカルの動画ファイルからやり直す")
    youtube_resume.add_argument("publication_id")
    youtube_resume.add_argument("--keep-video", action="store_true")
    youtube_resume.set_defaults(func=_cmd_youtube_resume)

    args = parser.parse_args()
    try:
        return args.func(args)
    except (
        AudioSourceError,
        DataRepoError,
        FormatError,
        ItemValidationError,
        PublishError,
        TTSEngineError,
        VideoError,
        VocabFetchError,
        WorksheetError,
        YouTubeConfigError,
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
