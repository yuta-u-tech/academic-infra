#!/usr/bin/env python3
"""TOEIC 解答提出用 Google Form の作成。

日次バッチの手順は「問題データ生成 → Form作成 → TeX生成」の順を厳守すること
（docs/2026-08-09-toeic-forms-integration.md 参照）。TeX側にFormのURLを埋め込む
処理（academic_audio / toeic_reading の render）はこの後に呼ぶ。

    python3 scripts/toeic_forms_cli.py create --items items.json --type choice \
        --title "Part2 2026-08-09" --out .toeic-forms/sets/20260809-part2 \
        --allowed-email friend@example.com

items.json の形式:
    {"items": [{"kind": "choice", "review_id": "...", "topic": "...", "difficulty": 3,
                "question": "...", "choices": ["...", "..."], "answer_index": 0,
                "explanation": "..."}, ...]}
  記述式(--type free)は choices/answer_index の代わりに model_answer を持つ。

出力（--out 配下）:
    form_map.json  — {"form_id", "responder_url", "edit_url", "items": {review_id: {...itemId...}}}

翌朝バッチ（選択式のみ対応。記述式の自己採点記録は未実装）:

    python3 scripts/toeic_forms_cli.py record --form-map .toeic-forms/sets/20260809-part2/form_map.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _drive_common  # noqa: E402
import _forms_common  # noqa: E402
from acenglish import study  # noqa: E402
from acenglish.db import connect  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from toeic_forms.builder import build_choice_quiz_requests, build_free_response_requests  # noqa: E402
from toeic_forms.client import apply_requests, create_form, edit_url, list_responses, responder_url, restrict_access  # noqa: E402
from toeic_forms.items import ChoiceFormItem, FreeFormItem  # noqa: E402
from toeic_forms.reflect import extract_answers  # noqa: E402


def _load_items(path: Path, item_type: str) -> list:
    payload = json.loads(path.read_text(encoding="utf-8"))
    model = ChoiceFormItem if item_type == "choice" else FreeFormItem
    try:
        items = [model.model_validate(entry) for entry in payload["items"]]
    except ValidationError as error:
        raise SystemExit(f"items の形式が不正です:\n{error}")
    if not items:
        raise SystemExit("items が空です。")
    return items


def _cmd_create(args: argparse.Namespace) -> int:
    items = _load_items(args.items, args.type)

    if args.type == "choice":
        requests, item_map = build_choice_quiz_requests(items)
    else:
        requests, item_map = build_free_response_requests(items)

    forms_credentials = _forms_common.resolve_credentials()
    forms_service = _forms_common.build_service(forms_credentials)

    form_id = create_form(forms_service, args.title)
    apply_requests(forms_service, form_id, requests)

    if args.allowed_email:
        drive_credentials = _drive_common.resolve_credentials()
        drive_service = _drive_common.build_service(drive_credentials)
        restrict_access(drive_service, form_id, args.allowed_email)

    args.out.mkdir(parents=True, exist_ok=True)
    out_path = args.out / "form_map.json"
    out_path.write_text(
        json.dumps(
            {
                "form_id": form_id,
                "responder_url": responder_url(form_id),
                "edit_url": edit_url(form_id),
                "type": args.type,
                "items": item_map,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Form作成: {responder_url(form_id)}")
    print(f"form_map: {out_path}")
    return 0


def _cmd_record(args: argparse.Namespace) -> int:
    form_map = json.loads(args.form_map.read_text(encoding="utf-8"))
    if form_map.get("type") != "choice":
        raise SystemExit(
            "record は選択式(type=choice)のFormのみ対応です"
            "（記述式の自己採点記録は docs/2026-08-09-toeic-forms-integration.md の未実装項目）。"
        )

    forms_credentials = _forms_common.resolve_credentials()
    forms_service = _forms_common.build_service(forms_credentials)
    responses = list_responses(forms_service, form_map["form_id"])
    answers = extract_answers(form_map["items"], responses)

    if not answers:
        print(json.dumps({"recorded": 0, "results": []}, ensure_ascii=False, indent=2))
        return 0

    connection = connect(args.db) if args.db else connect()
    try:
        session_id = study.start_session(connection, args.course_id, note=f"form:{form_map['form_id']}")
        results = []
        for answer in answers:
            try:
                outcome = study.record_form_response(connection, session_id, answer["review_id"], answer["response"])
            except LookupError as error:
                results.append({"review_id": answer["review_id"], "error": str(error)})
                continue
            results.append({"review_id": answer["review_id"], "correct": outcome.correct})
        study.end_session(connection, session_id)
    finally:
        connection.close()

    print(json.dumps({"recorded": len(results), "results": results}, ensure_ascii=False, indent=2))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Formを作成する")
    create.add_argument("--items", type=Path, required=True)
    create.add_argument("--type", choices=("choice", "free"), required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--out", type=Path, required=True, help="form_map.json の出力先ディレクトリ")
    create.add_argument(
        "--allowed-email",
        action="append",
        default=[],
        help="回答を許可するGoogleアカウント（複数指定可）。未指定なら共有設定を変更しない",
    )
    create.set_defaults(func=_cmd_create)

    record = subparsers.add_parser("record", help="Formの回答を読み取り english.db へ反映する（選択式のみ）")
    record.add_argument("--form-map", type=Path, required=True, help="create で出力した form_map.json")
    record.add_argument("--db", type=Path, help="english.db のパス（既定: ACADEMIC_ENGLISH_HOME）")
    record.add_argument("--course-id", default="toeic")
    record.set_defaults(func=_cmd_record)

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
