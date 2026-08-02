#!/usr/bin/env python3
"""英語学習機能のCLI。pm-desk（Claude）からはこのスクリプトだけを叩く。

    # 学習対象を見る
    python3 scripts/acenglish_cli.py targets --course dsa

    # 生成依頼を出す（Claude がこのJSONを読んで生成物を書く）
    python3 scripts/acenglish_cli.py request --review-id dsa.ch02.list.s01 --kind vocab,reading \
        --out /tmp/request.json

    # Claude が書いた生成物を取り込む
    python3 scripts/acenglish_cli.py ingest --file /tmp/result.json

    # 学習UIを起動する（127.0.0.1 のみ）
    python3 scripts/acenglish_cli.py serve

    # 資料への追記候補を findings.json に出す（→ promote_drive_comments.py へ渡す）
    python3 scripts/acenglish_cli.py findings --course dsa --out /tmp/findings.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _data_repo import DataRepoError, commit_and_push, data_repo_path  # noqa: E402
from acenglish import fetch, generate, notes, promote  # noqa: E402
from acenglish.api import DEFAULT_HOST, DEFAULT_PORT, NonLoopbackBindError  # noqa: E402
from acenglish.db import backup, connect, database_path  # noqa: E402
from acenglish.items import write_json_schemas  # noqa: E402
from acenglish.sources import studyforge  # noqa: E402
from acenglish.sources.studyforge import DeckNotFoundError  # noqa: E402
from acenglish.sources.ted import SubtitleNotFoundError, YtDlpNotInstalledError  # noqa: E402
from acenglish.sources.voa import ArticleFetchError  # noqa: E402
from acenglish.notes import NotesRepositoryError  # noqa: E402
from acenglish.target import (  # noqa: E402
    ManifestNotFoundError,
    TargetNotFoundError,
    get_target,
    list_targets,
    resolve_course_id,
)
from _drive_common import CourseNotFoundError  # noqa: E402
from pydantic import ValidationError  # noqa: E402


def _cmd_targets(args: argparse.Namespace) -> int:
    course_id = resolve_course_id(args.course)
    targets = list_targets(course_id, args.repo_root)
    print(
        json.dumps(
            {
                "course_id": course_id,
                "targets": [
                    {
                        "review_id": t.review_id,
                        "title": t.title,
                        "chapter": t.chapter_title,
                        "section_file": t.section_file,
                        "chars": len(t.body),
                    }
                    for t in targets
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _resolve_any(args: argparse.Namespace, review_id: str, course: str | None):
    """科目資料と外部素材のどちらでも学習対象を返す。"""
    with connect(args.db) as connection:
        external = fetch.load_material(connection, review_id)
    if external is not None:
        return external
    return get_target(review_id, course and resolve_course_id(course), args.repo_root)


def _cmd_request(args: argparse.Namespace) -> int:
    target = _resolve_any(args, args.review_id, args.course)
    kinds = [k.strip() for k in args.kind.split(",") if k.strip()]
    with connect(args.db) as connection:
        generate.upsert_material(connection, target)
        retired = generate.retire_stale(connection, target.review_id, target.source_commit)
    path = generate.write_request(target, kinds, args.out, args.count)
    print(f"生成依頼: {path}")
    if retired:
        print(f"退役: 古い版の未検証生成物 {retired} 件")
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    result = generate.load_result(args.file)
    target = _resolve_any(args, result.review_id, result.course_id)
    with connect(args.db) as connection:
        generate.upsert_material(connection, target)
        item_ids = generate.ingest(connection, result)
    print(f"取り込み: {len(item_ids)} 件 (item_id: {', '.join(map(str, item_ids))})")
    return 0


def _cmd_findings(args: argparse.Namespace) -> int:
    course_id = resolve_course_id(args.course) if args.course else None
    with connect(args.db) as connection:
        path, ids = promote.export_findings(connection, args.out, course_id)
        if args.mark_promoted:
            promote.mark_promoted(connection, ids)
    if not ids:
        print("追記候補はありません。")
        return 0
    print(f"追記候補 {len(ids)} 件を書き出しました: {path}")
    print(
        "Issue化: python3 scripts/promote_drive_comments.py "
        f"--course {course_id or '<course>'} --findings {path} --pick 1 --no-drive-reply"
    )
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    from acenglish.api import run

    try:
        run(args.host, args.port, args.db)
    except NonLoopbackBindError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


def _cmd_backup(args: argparse.Namespace) -> int:
    out = args.out or (data_repo_path() / "backups" / f"english-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.db")
    snapshot = backup(out, args.db)
    print(f"バックアップ: {snapshot}")
    if args.push:
        try:
            pushed = commit_and_push(data_repo_path(), [snapshot], f"backup: {snapshot.name}")
        except DataRepoError as error:
            print(f"push できませんでした: {error}", file=sys.stderr)
            return 1
        print("push: 完了" if pushed else "push: 差分なし")
    return 0


def _cmd_schema(args: argparse.Namespace) -> int:
    for path in write_json_schemas():
        print(f"書き出し: {path}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    with connect(args.db) as connection:
        counts = {
            table: connection.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            for table in ("material", "generated_item", "attempt", "skill_state", "revision_candidate")
        }
    print(json.dumps({"database": str(database_path()), "counts": counts}, ensure_ascii=False, indent=2))
    return 0



def _cmd_fetch_toeic(args: argparse.Namespace) -> int:
    total = 0
    decks = args.deck.split(",") if args.deck else list(studyforge.DECKS)
    with connect(args.db) as connection:
        for deck in decks:
            imported = fetch.import_toeic_deck(connection, deck.strip(), args.limit)
            total += imported
            print(f"{deck.strip()}: 新規 {imported} 語")
    print(f"合計 {total} 語を取り込みました。")
    return 0


def _cmd_voa(args: argparse.Namespace) -> int:
    if args.url:
        with connect(args.db) as connection:
            material = fetch.import_voa_article(connection, args.url, args.title or "")
        print(f"取り込み: {material.review_id}  {material.title}")
        print(f"次: acenglish_cli.py request --review-id {material.review_id} "
              f"--kind reading,grammar,vocab --out /tmp/req.json")
        return 0

    articles = fetch.list_voa_articles(args.feed, args.limit)
    print(json.dumps({"articles": articles}, ensure_ascii=False, indent=2))
    return 0


def _cmd_ted(args: argparse.Namespace) -> int:
    with connect(args.db) as connection:
        material = fetch.import_ted_talk(connection, args.url, args.max_sentences)
    print(f"取り込み: {material.review_id}  {material.title}")
    print(f"次: acenglish_cli.py request --review-id {material.review_id} "
          f"--kind vocab,reading --out /tmp/req.json")
    return 0


def _cmd_note_draft(args: argparse.Namespace) -> int:
    with connect(args.db) as connection:
        written = notes.write_drafts(connection, args.notes_home, args.mark_promoted)
    print(notes.summarize(written))
    if written:
        print(f"確認して {written[0].parent.parent} の notes/ へ反映してください。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=None, help="SQLiteのパス（既定: ~/.academic-english/english.db）")
    subparsers = parser.add_subparsers(dest="command", required=True)

    targets = subparsers.add_parser("targets", help="学習対象のセクション一覧")
    targets.add_argument("--course", required=True)
    targets.add_argument("--repo-root", type=Path, help="科目リポジトリのパス（既定: lecture.yml）")
    targets.set_defaults(func=_cmd_targets)

    request = subparsers.add_parser("request", help="生成依頼JSONを書き出す")
    request.add_argument("--review-id", required=True)
    request.add_argument("--course")
    request.add_argument("--kind", default="vocab,reading")
    request.add_argument("--count", type=int, default=5)
    request.add_argument("--out", type=Path, required=True)
    request.add_argument("--repo-root", type=Path)
    request.set_defaults(func=_cmd_request)

    ingest = subparsers.add_parser("ingest", help="生成結果を検証して取り込む")
    ingest.add_argument("--file", type=Path, required=True)
    ingest.add_argument("--repo-root", type=Path)
    ingest.set_defaults(func=_cmd_ingest)

    findings = subparsers.add_parser("findings", help="追記候補を findings.json に出す")
    findings.add_argument("--course")
    findings.add_argument("--out", type=Path, required=True)
    findings.add_argument("--mark-promoted", action="store_true", help="出力と同時に候補を閉じる")
    findings.set_defaults(func=_cmd_findings)

    serve = subparsers.add_parser("serve", help="学習UIを起動する（127.0.0.1のみ）")
    serve.add_argument("--host", default=DEFAULT_HOST)
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.set_defaults(func=_cmd_serve)

    backup_parser = subparsers.add_parser("backup", help="SQLiteのスナップショットを取る")
    backup_parser.add_argument("--out", type=Path, help="既定: academic-english-data/backups/english-<UTC>.db")
    backup_parser.add_argument("--push", action="store_true", help="取った後 academic-english-data へ commit + push する")
    backup_parser.set_defaults(func=_cmd_backup)

    schema = subparsers.add_parser("schema", help="JSON Schema を書き出す")
    schema.set_defaults(func=_cmd_schema)

    fetch_toeic = subparsers.add_parser("fetch-toeic", help="TOEIC語彙(study-forge)を取り込む")
    fetch_toeic.add_argument("--deck", help=f"カンマ区切り（既定: 全部）対応: {', '.join(studyforge.DECKS)}")
    fetch_toeic.add_argument("--limit", type=int, help="各デッキの先頭N語だけ")
    fetch_toeic.set_defaults(func=_cmd_fetch_toeic)

    voa_parser = subparsers.add_parser("voa", help="VOA Learning English（URL省略で記事一覧）")
    voa_parser.add_argument("--url", help="記事URL。省略するとRSSから一覧を出す")
    voa_parser.add_argument("--title")
    voa_parser.add_argument("--feed", help="RSSのURL（省略時は一覧ページの先頭）")
    voa_parser.add_argument("--limit", type=int, default=10)
    voa_parser.set_defaults(func=_cmd_voa)

    ted_parser = subparsers.add_parser("ted", help="TED/YouTubeの字幕を取り込む")
    ted_parser.add_argument("--url", required=True)
    ted_parser.add_argument("--max-sentences", type=int, default=60)
    ted_parser.set_defaults(func=_cmd_ted)

    note = subparsers.add_parser("note-draft", help="英語ノートへの追記候補を drafts/ に書く")
    note.add_argument("--notes-home", type=Path, help="既定: ~/english-notes")
    note.add_argument("--mark-promoted", action="store_true")
    note.set_defaults(func=_cmd_note_draft)

    status = subparsers.add_parser("status", help="DBの件数を見る")
    status.set_defaults(func=_cmd_status)

    args = parser.parse_args()
    try:
        return args.func(args)
    except (CourseNotFoundError, ManifestNotFoundError, TargetNotFoundError,
            generate.UnknownKindError, DeckNotFoundError, ArticleFetchError,
            SubtitleNotFoundError, YtDlpNotInstalledError, NotesRepositoryError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except ValidationError as error:
        print(f"生成物がスキーマに適合しません:\n{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
