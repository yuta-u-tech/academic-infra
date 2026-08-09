"""toeic_forms_cli.py record の一気通貫テスト（Forms APIはモック、english.dbは実物）。"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import toeic_forms_cli as cli  # noqa: E402
from acenglish.db import connect  # noqa: E402
from acenglish.fetch import import_toeic_part5  # noqa: E402
from acenglish.items import GrammarItem  # noqa: E402

ITEM = GrammarItem.model_validate(
    {
        "sentence": "The manager ____ the report yesterday.",
        "choices": ["submit", "submits", "submitted", "submitting"],
        "answer_index": 2,
        "explanation": "過去の出来事なので過去形。",
        "point": "時制",
        "pattern": "A",
        "pattern_note": "同じ語(submit)の語形違いのみで構成しているため。",
    }
)


def _build_args(form_map_path: Path, db_path: Path):
    parser = cli._build_parser()
    return parser.parse_args(
        ["record", "--form-map", str(form_map_path), "--db", str(db_path), "--course-id", "toeic"]
    )


def test_record_scores_a_correct_response_and_writes_to_english_db(tmp_path, monkeypatch):
    db_path = tmp_path / "english.db"
    connection = connect(db_path)
    import_toeic_part5(connection, "20260809", [ITEM])
    review_id = connection.execute(
        "SELECT review_id FROM generated_item WHERE kind = 'grammar' LIMIT 1"
    ).fetchone()["review_id"]
    connection.close()

    form_map = {
        "form_id": "fake-form-id",
        "responder_url": "https://example.invalid/viewform",
        "edit_url": "https://example.invalid/edit",
        "type": "choice",
        "items": {
            review_id: {"question_item_id": "q1", "choices": ITEM.choices},
        },
    }
    form_map_path = tmp_path / "form_map.json"
    form_map_path.write_text(json.dumps(form_map), encoding="utf-8")

    monkeypatch.setattr(cli._forms_common, "resolve_credentials", lambda: {})
    monkeypatch.setattr(cli._forms_common, "build_service", lambda credentials: object())
    monkeypatch.setattr(
        cli,
        "list_responses",
        lambda forms_service, form_id: [
            {
                "responseId": "r1",
                "answers": {"q1": {"textAnswers": {"answers": [{"value": "submitted"}]}}},
            }
        ],
    )

    args = _build_args(form_map_path, db_path)
    exit_code = args.func(args)
    assert exit_code == 0

    connection = connect(db_path)
    attempt = connection.execute("SELECT correct, response FROM attempt WHERE review_id = ?", (review_id,)).fetchone()
    connection.close()
    assert attempt["correct"] == 1
    assert attempt["response"] == "2"


def test_record_rejects_free_type_form_maps(tmp_path, monkeypatch):
    form_map = {"form_id": "x", "type": "free", "items": {}}
    form_map_path = tmp_path / "form_map.json"
    form_map_path.write_text(json.dumps(form_map), encoding="utf-8")

    args = _build_args(form_map_path, tmp_path / "english.db")
    try:
        args.func(args)
        assert False, "SystemExit を期待した"
    except SystemExit as error:
        assert "選択式" in str(error)
