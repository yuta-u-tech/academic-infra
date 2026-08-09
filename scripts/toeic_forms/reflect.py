"""Forms API の回答一覧を english.db への記録用データへ変換する（純粋関数）。

Google Sheets ではなく Forms API の `forms.responses.list()` を直接読む。
`forms.responses.readonly` スコープだけで完結し、Sheets API 用の追加スコープ・
リンク済みスプレッドシートの解決が要らないため
（docs/2026-08-09-toeic-forms-integration.md の当初想定から簡略化した）。
"""
from __future__ import annotations


class ReflectError(Exception):
    pass


def extract_answers(form_map_items: dict[str, dict], responses: list[dict]) -> list[dict]:
    """review_id ごとの提出済み回答を返す（未提出はスキップ）。

    choices を持つ設問（選択式）は Forms が返す選択肢の**テキスト値**を
    `answer_index` 形式の文字列（"0"/"1"/...）に変換する
    （acenglish.items.GrammarItem/ReadingItem.check() が int(response) で比較するため）。
    同じ設問に複数のresponseが来た場合（出し直し等）は、`responses` の並び順で
    最後に見つかったものを採用する（Forms API は提出時刻の昇順で返す前提）。
    """
    latest: dict[str, dict] = {}
    for response in responses:
        answers = response.get("answers", {})
        for review_id, mapping in form_map_items.items():
            item_id = mapping.get("question_item_id")
            answer = answers.get(item_id)
            if answer is None:
                continue
            text_answers = answer.get("textAnswers", {}).get("answers", [])
            if not text_answers:
                continue
            value = text_answers[0].get("value", "")

            choices = mapping.get("choices")
            if choices:
                try:
                    response_value = str(choices.index(value))
                except ValueError:
                    raise ReflectError(
                        f"review_id={review_id} の回答値 {value!r} が choices={choices} にありません。"
                    )
            else:
                response_value = value

            latest[review_id] = {
                "review_id": review_id,
                "response": response_value,
                "response_id": response.get("responseId"),
            }
    return list(latest.values())
