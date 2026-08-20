#!/usr/bin/env python3
"""TOEIC 単語テスト CLI（語彙MCQ、生成不要・冪等）。

TOEIC語彙（`acenglish_cli.py fetch-toeic` で取り込み済みの2,282語）から、
シャッフル済みの順序を状態として持ち回りながら1日分（既定100問）を切り出して
問題冊子PDFを組む。1サイクル（プール全体、約23日分）を出し切ったら自動的に
再シャッフルして次のサイクルへ入るため、「毎日ランダムだが同じサイクル内では
重複しない」出題になる。

**苦手語の再出題（2026-08-10追加）**: `--weak-count`（既定20）で、直近の回答が
不正解だった語を毎回そのぶんだけ優先的に混ぜる。Forms解答提出で`attempt`に
正誤が残るようになったことで実現した（`acenglish.vocab_quiz.weak_review_ids()`が
`toeic_forms_cli.py record`後のattemptを見て決定論的に選ぶ。文脈判断が要らないので
Claudeは介在しない）。既に克服した語（最新の回答が正解）は対象から外れる。

    python3 scripts/toeic_vocab_cli.py build --count 100 --out .toeic-vocab/sets/20260806
    python3 scripts/toeic_vocab_cli.py publish --pdf .toeic-vocab/sets/20260806/worksheet.pdf

Google Forms連携（任意・実装済み2026-08-10）。手順は build → Form変換・作成 →
attach-form-url → publish の順を厳守する（Form作成より前に冊子へURLを埋め込めないため）。
語彙は`fetch-toeic`で取り込み済みのVocabItemが既にDBにあるため、Part5/Part7と違い
別途ingestは不要（build時のreview_idがそのままgenerated_itemのreview_idと一致する）:

    # build後、items.json の各問題を choice型Form用スキーマ（question=word,
    # choices=meaning群, answer_index, explanation）に変換してから作成する
    # （Part5/Part7と同じくこの変換はClaudeがその都度書く。専用コマンドは無い）
    python3 scripts/toeic_forms_cli.py create --items <変換後>.json --type choice \
        --title "語彙テスト 2026-08-06" --out .toeic-forms/sets/20260806-vocab \
        --allowed-email <許可アカウント>

    python3 scripts/toeic_vocab_cli.py attach-form-url --set-dir .toeic-vocab/sets/20260806 \
        --form-url <2で得たresponder_url>

    # 回答が出揃ったら（record は選択式Formなら他のTOEIC教材と共通）
    python3 scripts/toeic_forms_cli.py record --form-map .toeic-forms/sets/20260806-vocab/form_map.json

語彙テストは選択肢が出題のたびにランダムに組み直されるため、generated_item
（VocabItem）自身は正解choicesを持たない。record時の採点は form_map.json 側に
保存された answer_index を使う（acenglish.study.answer() の correct_override 経路。
item.check() には依存しない）。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acenglish import study  # noqa: E402
from acenglish.db import connect  # noqa: E402
from acenglish.vocab_quiz import (  # noqa: E402
    build_choices,
    load_pool,
    load_pool_by_direction,
    next_batch,
    weak_review_ids,
)
from toeic_reading.flashcard_record import read_checked_review_ids, reset_checkboxes  # noqa: E402
from toeic_reading.flashcard_render import (  # noqa: E402
    FlashcardEntry,
    build_pdf as build_flashcard_pdf,
    render_flashcard_md,
    render_flashcard_tex,
)
from toeic_reading.flashcard_reveal import build_dual_checkbox_flashcards  # noqa: E402
from toeic_reading.vocab_render import QuizQuestion, build_pdf, render_md, render_tex  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")

DEFAULT_DRIVE_FOLDER_NAME = "TOEIC/vocabulary"
REVIEW_DRIVE_FOLDER_NAME = "TOEIC/review"


def _cmd_build(args: argparse.Namespace) -> int:
    today = datetime.now(JST).strftime("%Y-%m-%d")
    title = args.title or f"語彙テスト {today}"

    with connect(args.db) as connection:
        pool = load_pool(connection)
        if not pool:
            raise SystemExit(
                "語彙プールが空です。先に `acenglish_cli.py fetch-toeic` で取り込んでください。"
            )
        weak_ids = weak_review_ids(connection, limit=args.weak_count) if args.weak_count > 0 else []
        batch, state = next_batch(pool, args.count, home=args.home, weak_ids=weak_ids)

    questions = []
    for entry in batch:
        choices, answer_index = build_choices(entry, pool)
        questions.append(QuizQuestion(
            review_id=entry.review_id,
            word=entry.word,
            choices=choices,
            answer_index=answer_index,
            meaning=entry.meaning,
            example=entry.example,
        ))

    args.out.mkdir(parents=True, exist_ok=True)
    items_path = args.out / "items.json"
    items_path.write_text(
        json.dumps(
            {
                "title": title,
                "cycle": state["cycle"],
                "questions": [
                    {
                        "review_id": q.review_id,
                        "word": q.word,
                        "choices": q.choices,
                        "answer_index": q.answer_index,
                        "meaning": q.meaning,
                        "example": q.example,
                    }
                    for q in questions
                ],
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )

    tex_path = args.out / "worksheet.tex"
    tex_path.write_text(render_tex(title, questions), encoding="utf-8")
    pdf_path = build_pdf(tex_path)
    md_path = args.out / "worksheet.md"
    md_path.write_text(render_md(title, questions), encoding="utf-8")

    included_weak = [q.review_id for q in questions if q.review_id in set(weak_ids)]
    print(json.dumps(
        {
            "pdf": str(pdf_path),
            "md": str(md_path),
            "items": str(items_path),
            "count": len(questions),
            "cycle": state["cycle"],
            "pool_size": len(pool),
            "weak_requested": len(weak_ids),
            "weak_included": len(included_weak),
            "weak_review_ids": included_weak,
        },
        ensure_ascii=False, indent=2))
    return 0


def _cmd_attach_form_url(args: argparse.Namespace) -> int:
    """build 済みの --set-dir に、Google Form の回答URLを差し込んで worksheet を作り直す。

    `scripts/toeic_forms_cli.py create` で作った Form の responder_url を渡す想定
    （順序: build → items.json を Form 用スキーマへ変換して create → ここで埋め込み、を厳守）。
    state（出題の読み進み位置）は書き換えない。
    """
    items_path = args.set_dir / "items.json"
    if not items_path.exists():
        raise FileNotFoundError(f"{items_path} がありません。先に build を実行してください。")
    payload = json.loads(items_path.read_text(encoding="utf-8"))
    title = payload["title"]
    questions = [
        QuizQuestion(
            review_id=q["review_id"],
            word=q["word"],
            choices=q["choices"],
            answer_index=q["answer_index"],
            meaning=q["meaning"],
            example=q["example"],
        )
        for q in payload["questions"]
    ]

    tex_path = args.set_dir / "worksheet.tex"
    tex_path.write_text(render_tex(title, questions, form_url=args.form_url), encoding="utf-8")

    result = {"worksheet_tex": str(tex_path)}
    if not args.no_pdf:
        result["worksheet_pdf"] = str(build_pdf(tex_path))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_flashcards(args: argparse.Namespace) -> int:
    """プールの一部または全部を、開閉式(タップで訳を表示)＋自己採点チェック付きの単語帳PDFにまとめる。

    build（4択・Forms提出、1日分だけを毎日ローテーションする別機能）とは違い、
    語彙プールに登録済みの語をまとめて1冊にする。単語が増える（import-tex-vocab等）
    たびに実行し直せば、その時点の全語を反映した1冊に更新される。
    「英単語を見て意味を思い出せるか」を試す形（推奨→自己採点recognition方向）なので、
    既定では sub_skill=recognition の行だけを対象にする（1語1行になる。recall方向の
    複製行まで混ぜると同じ語が2回出てしまうため）。

    **章分け（2026-08-20追加）**: `--start`/`--limit` でプール中の範囲を切り出せる。
    Google Driveアプリ内蔵のPDFフォーム入力機能で1ファイル4000語超のAcroFormを編集すると、
    保存時にフィールド対応がずれて無関係な語のチェック状態が壊れる事故が実際に起きたため
    （2026-08-20実機確認）、数百語単位で複数ファイルに分けて配布する運用に切り替える。
    章ごとに `items.json` も分かれるため、`record-flashcards` はその章の語だけを対象に
    記録する（未着手の章の語を「正解」と誤記録する心配がない）。
    """
    title = args.title or "TOEIC 単語帳（全語）"

    with connect(args.db) as connection:
        pool = load_pool_by_direction(connection, args.direction)
        if not pool:
            raise SystemExit(
                "語彙プールが空です。先に `acenglish_cli.py fetch-toeic` "
                "（および必要なら duplicate-vocab-direction）で取り込んでください。"
            )

    start = max(args.start - 1, 0)
    end = start + args.limit if args.limit else len(pool)
    chapter = pool[start:end]
    if not chapter:
        raise SystemExit(f"--start {args.start} はプール件数({len(pool)})の範囲外です。")

    entries = [
        FlashcardEntry(review_id=e.review_id, word=e.word, meaning=e.meaning, example=e.example)
        for e in chapter
    ]

    args.out.mkdir(parents=True, exist_ok=True)
    items_path = args.out / "items.json"
    items_path.write_text(
        json.dumps(
            {
                "title": title,
                "start": args.start,
                "entries": [
                    {"review_id": e.review_id, "word": e.word, "meaning": e.meaning, "example": e.example}
                    for e in entries
                ],
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )

    pdf_path = build_dual_checkbox_flashcards(title, entries, args.out)
    md_path = args.out / "flashcards.md"
    md_path.write_text(render_flashcard_md(title, entries), encoding="utf-8")

    print(json.dumps(
        {
            "pdf": str(pdf_path),
            "md": str(md_path),
            "items": str(items_path),
            "count": len(entries),
            "start": args.start,
            "direction": args.direction,
        },
        ensure_ascii=False, indent=2))
    return 0


def _cmd_review_flashcards(args: argparse.Namespace) -> int:
    """「分からなかった」（直近の回答が不正解）の語だけを集めた復習単語帳を組む。

    プールの読み進み位置（next_batch の state）は一切動かさない。record-flashcards で
    正解に変わった語は weak_review_ids() から自然に外れるため、ここを実行するたびに
    その時点の最新状態を反映した単語帳になる（TOEIC/review へは固定ファイル名で
    publish する運用を想定 — 日付ではなく上書きで「更新していく」）。
    """
    with connect(args.db) as connection:
        pool = load_pool(connection)
        by_id = {e.review_id: e for e in pool}
        weak_ids = weak_review_ids(connection, limit=args.limit)

    entries = [
        FlashcardEntry(
            review_id=rid, word=by_id[rid].word, meaning=by_id[rid].meaning, example=by_id[rid].example
        )
        for rid in weak_ids if rid in by_id
    ]
    if not entries:
        print(json.dumps({"count": 0, "message": "現在、要復習の単語はありません。"}, ensure_ascii=False))
        return 0

    title = args.title or "TOEIC 復習単語帳"
    args.out.mkdir(parents=True, exist_ok=True)
    items_path = args.out / "items.json"
    items_path.write_text(
        json.dumps(
            {
                "title": title,
                "entries": [
                    {"review_id": e.review_id, "word": e.word, "meaning": e.meaning, "example": e.example}
                    for e in entries
                ],
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )

    tex_path = args.out / "flashcards.tex"
    tex_path.write_text(render_flashcard_tex(title, entries), encoding="utf-8")
    pdf_path = build_flashcard_pdf(tex_path)
    md_path = args.out / "flashcards.md"
    md_path.write_text(render_flashcard_md(title, entries), encoding="utf-8")

    print(json.dumps(
        {"pdf": str(pdf_path), "md": str(md_path), "items": str(items_path), "count": len(entries)},
        ensure_ascii=False, indent=2))
    return 0


def _cmd_record_flashcards(args: argparse.Namespace) -> int:
    """チェック済みの単語帳PDFを読み、学習ループへ記録する。

    「分からなかった」にチェック=不正解、無印=正解として correct_override 経路で
    記録する（record_form_response と同じ、study.answer() の閉ループを通す）。
    記録後、正誤に関わらずチェック状態を全て空にしたコピーを --reset-out に書き出せる
    （同じPDFファイルを次のラウンドでも使い回したい場合用）。
    """
    payload = json.loads(args.items.read_text(encoding="utf-8"))
    entries = payload["entries"]
    checked = read_checked_review_ids(args.pdf)

    connection = connect(args.db) if args.db else connect()
    try:
        session_id = study.start_session(connection, args.course_id, note=f"flashcards:{args.pdf.name}")
        results = []
        for entry in entries:
            review_id = entry["review_id"]
            correct = review_id not in checked
            response = "分からなかった" if not correct else "分かった"
            try:
                outcome = study.record_form_response(
                    connection, session_id, review_id, response, correct_override=correct,
                )
            except LookupError as error:
                results.append({"review_id": review_id, "error": str(error)})
                continue
            results.append({"review_id": review_id, "correct": outcome.correct})
        study.end_session(connection, session_id)
    finally:
        connection.close()

    reset_pdf = None
    if args.reset_out:
        review_ids = [e["review_id"] for e in entries]
        reset_pdf = str(reset_checkboxes(args.pdf, args.reset_out, review_ids))

    print(json.dumps(
        {
            "recorded": len(results),
            "known": sum(1 for r in results if r.get("correct") is True),
            "unknown": sum(1 for r in results if r.get("correct") is False),
            "results": results,
            "reset_pdf": reset_pdf,
        },
        ensure_ascii=False, indent=2))
    return 0


def _cmd_publish(args: argparse.Namespace) -> int:
    import _drive_common

    if not args.pdf.exists():
        raise FileNotFoundError(f"{args.pdf} がありません。先に build を実行してください。")

    today = datetime.now(JST).strftime("%Y-%m-%d")
    drive_name = args.name or f"{today}.pdf"
    folder_names = [part for part in args.folder_name.split("/") if part]
    drive_path = "/".join([*folder_names, drive_name])

    md_path = args.pdf.with_suffix(".md")
    md_folder_names = [*folder_names[:-1], "MDs"] if len(folder_names) > 1 else ["MDs"]
    # --name で固定ファイル名を指定した場合（flashcards/review-flashcardsのように
    # 上書き更新する運用）は、MD側もPDFと同じstemに揃える。日付固定のままだと
    # 更新のたびにMDだけ増え続けてしまう。MDは複数フォルダ分を共有の「MDs」1箇所へ
    # 集約するため、フォルダ名（例: vocabulary/review）をstemの前に付けて衝突を避ける
    # （2026-08-19、vocabulary用とreview用が両方 "flashcards.md" になり、後勝ちで
    # 上書き事故が実際に発生した）。
    part_label = folder_names[-1] if folder_names else None
    if args.name and part_label:
        md_drive_name = f"{part_label}-{Path(drive_name).stem}.md"
    elif args.name:
        md_drive_name = f"{Path(drive_name).stem}.md"
    else:
        md_drive_name = f"{today}.md"
    md_drive_path = "/".join([*md_folder_names, md_drive_name]) if md_path.exists() else None

    if args.dry_run:
        print(json.dumps(
            {
                "dry_run": True,
                "drive_path": drive_path,
                "local": str(args.pdf),
                "md_drive_path": md_drive_path,
                "md_local": str(md_path) if md_path.exists() else None,
            },
            ensure_ascii=False, indent=2))
        return 0

    credentials = _drive_common.resolve_credentials()
    parent_id = args.parent_id or credentials.get("GDRIVE_PARENT_FOLDER_ID", "")
    if not parent_id:
        raise ValueError("--parent-id か GDRIVE_PARENT_FOLDER_ID が必要です。")

    service = _drive_common.build_service(credentials)
    folder_id = parent_id
    for name in folder_names:
        folder_id = _drive_common.ensure_folder(service, folder_id, name)
    file_id = _drive_common.upload_file(service, folder_id, args.pdf, "application/pdf", name=drive_name)

    md_file_id = None
    if md_path.exists():
        md_folder_id = parent_id
        for name in md_folder_names:
            md_folder_id = _drive_common.ensure_folder(service, md_folder_id, name)
        md_file_id = _drive_common.upload_file(service, md_folder_id, md_path, "text/markdown", name=md_drive_name)

    print(json.dumps(
        {
            "drive_path": drive_path,
            "file_id": file_id,
            "url": f"https://drive.google.com/file/d/{file_id}/view",
            "md_drive_path": md_drive_path,
            "md_file_id": md_file_id,
            "md_url": f"https://drive.google.com/file/d/{md_file_id}/view" if md_file_id else None,
        },
        ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="今日分の語彙テストPDFを組む（状態を1回分進める）")
    build.add_argument("--count", type=int, default=100, help="1回の出題数（既定100）")
    build.add_argument(
        "--weak-count", type=int, default=20,
        help="直近の回答が不正解だった語を優先的に混ぜる件数（既定20。0で無効化）",
    )
    build.add_argument("--out", type=Path, required=True, help="出力先ディレクトリ")
    build.add_argument("--title", help="既定: 語彙テスト <日付>")
    build.add_argument("--db", type=Path, default=None, help="既定: ~/.academic-english/english.db")
    build.add_argument("--home", type=Path, default=None, help="状態ファイルの置き場所。既定: ~/.academic-english")
    build.set_defaults(func=_cmd_build)

    attach_form_url = sub.add_parser(
        "attach-form-url", help="toeic_forms_cli.py create で得た回答フォームURLを冊子に載せて作り直す"
    )
    attach_form_url.add_argument("--set-dir", type=Path, required=True, help="build の出力先")
    attach_form_url.add_argument("--form-url", required=True)
    attach_form_url.add_argument("--no-pdf", action="store_true")
    attach_form_url.set_defaults(func=_cmd_attach_form_url)

    publish = sub.add_parser("publish", help="問題冊子PDFを Drive へ上げる")
    publish.add_argument("--pdf", type=Path, required=True)
    publish.add_argument("--folder-name", default=DEFAULT_DRIVE_FOLDER_NAME, help="Drive 上のフォルダパス（/ 区切り）")
    publish.add_argument("--name", help="Drive 上のファイル名（既定: <当日の日付>.pdf）")
    publish.add_argument("--parent-id", help="既定は GDRIVE_PARENT_FOLDER_ID")
    publish.add_argument("--dry-run", action="store_true")
    publish.set_defaults(func=_cmd_publish)

    flashcards = sub.add_parser(
        "flashcards", help="プールの一部/全部を開閉式チェックボックス付き単語帳PDFにまとめる"
    )
    flashcards.add_argument(
        "--direction", default="recognition", choices=["recall", "recognition"],
        help="収録する方向（既定: recognition＝英単語を見て意味を思い出す形）",
    )
    flashcards.add_argument(
        "--start", type=int, default=1,
        help="プール中の開始位置（1始まり、既定1）。章分けするときに使う",
    )
    flashcards.add_argument(
        "--limit", type=int, default=None,
        help="この章に含める件数（既定: 開始位置から最後まで全部）",
    )
    flashcards.add_argument("--out", type=Path, required=True, help="出力先ディレクトリ")
    flashcards.add_argument("--title", help="既定: TOEIC 単語帳（全語）")
    flashcards.add_argument("--db", type=Path, default=None, help="既定: ~/.academic-english/english.db")
    flashcards.set_defaults(func=_cmd_flashcards)

    review_flashcards = sub.add_parser(
        "review-flashcards",
        help="直近の回答が不正解だった語だけの復習単語帳を組む（読み進み位置は動かさない）",
    )
    review_flashcards.add_argument("--limit", type=int, default=200, help="収録件数の上限（既定200）")
    review_flashcards.add_argument("--out", type=Path, required=True, help="出力先ディレクトリ")
    review_flashcards.add_argument("--title", help="既定: TOEIC 復習単語帳")
    review_flashcards.add_argument("--db", type=Path, default=None, help="既定: ~/.academic-english/english.db")
    review_flashcards.set_defaults(func=_cmd_review_flashcards)

    record_flashcards = sub.add_parser(
        "record-flashcards", help="チェック済みの単語帳PDFを読み、学習ループへ記録する"
    )
    record_flashcards.add_argument("--pdf", type=Path, required=True, help="チェックを入れて保存したPDF")
    record_flashcards.add_argument(
        "--items", type=Path, required=True, help="flashcards/review-flashcards が出力した items.json"
    )
    record_flashcards.add_argument("--course-id", default="english")
    record_flashcards.add_argument("--db", type=Path, default=None, help="既定: ~/.academic-english/english.db")
    record_flashcards.add_argument(
        "--reset-out", type=Path, default=None,
        help="指定すると、集計後に全チェックを外したコピーをこのパスへ書き出す（同じPDFの使い回し用）",
    )
    record_flashcards.set_defaults(func=_cmd_record_flashcards)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
