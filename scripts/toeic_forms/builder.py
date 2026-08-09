"""Google Forms API向けの batchUpdate リクエスト組み立て（純粋関数、ネットワーク呼び出し無し）。

選択式は quiz mode（自動採点+正誤時の解説表示）、記述式は
「自由記述 → 模範解答/解説 → 自己採点(3択)」の3セクション構成にする。

各設問の Forms 上の itemId は review_id から決定的に作る（Forms API の
createItem リクエストで itemId を明示指定できるため）。翌朝バッチが
スプレッドシートの回答行を review_id に逆引きするための対応表
（form_map）はこの決定的な id 生成のおかげで、Forms API のレスポンスを
パースしなくても作れる。
"""
from __future__ import annotations

import hashlib
import re

from .items import SELF_GRADE_OPTIONS, ChoiceFormItem, FreeFormItem

_ID_SANITIZE_RE = re.compile(r"[^a-zA-Z0-9]+")


def _make_item_id(review_id: str, suffix: str = "") -> str:
    """review_id から Forms の itemId を決定的に作る。

    review_id は `.` を含む（例: toeic.listening.part2.20260809.0001）ため、
    Forms が要求する識別子として扱いやすい形に正規化する。長さ超過や衝突を
    避けるため、末尾にreview_id全体の短いハッシュを付ける。
    """
    slug = _ID_SANITIZE_RE.sub("-", review_id).strip("-")[:40]
    digest = hashlib.sha1(review_id.encode("utf-8")).hexdigest()[:8]
    parts = [slug, digest]
    if suffix:
        parts.append(suffix)
    return "-".join(parts)


def build_choice_quiz_requests(
    items: list[ChoiceFormItem],
) -> tuple[list[dict], dict[str, dict[str, str]]]:
    """選択式(quiz mode)の batchUpdate リクエストと review_id→itemId 対応表を返す。"""
    requests: list[dict] = [
        {
            "updateSettings": {
                "settings": {"quizSettings": {"isQuiz": True}},
                "updateMask": "quizSettings.isQuiz",
            }
        }
    ]
    item_map: dict[str, dict[str, str]] = {}

    for index, item in enumerate(items):
        item_id = _make_item_id(item.review_id)
        item_map[item.review_id] = {"question_item_id": item_id}
        requests.append(
            {
                "createItem": {
                    "item": {
                        "itemId": item_id,
                        "title": item.question,
                        "questionItem": {
                            "question": {
                                "required": True,
                                "choiceQuestion": {
                                    "type": "RADIO",
                                    "options": [{"value": choice} for choice in item.choices],
                                    "shuffle": False,
                                },
                                "grading": {
                                    "pointValue": 1,
                                    "correctAnswers": {
                                        "answers": [{"value": item.choices[item.answer_index]}]
                                    },
                                    "whenRight": {"text": "正解です。"},
                                    "whenWrong": {"text": item.explanation},
                                },
                            }
                        },
                    },
                    "location": {"index": index},
                }
            }
        )
    return requests, item_map


def build_free_response_requests(
    items: list[FreeFormItem],
) -> tuple[list[dict], dict[str, dict[str, str]]]:
    """記述式(自己採点)の batchUpdate リクエストと review_id→itemId 対応表を返す。

    1問につき3アイテム（自由記述の設問 → 模範解答/解説の表示専用アイテム →
    自己採点の3択設問）を、pageBreakItem を挟んで直列に配置する。
    """
    requests: list[dict] = []
    item_map: dict[str, dict[str, str]] = {}
    index = 0

    for item in items:
        question_item_id = _make_item_id(item.review_id, "q")
        info_item_id = _make_item_id(item.review_id, "info")
        grade_item_id = _make_item_id(item.review_id, "grade")
        item_map[item.review_id] = {
            "question_item_id": question_item_id,
            "self_grade_item_id": grade_item_id,
        }

        # セクション1: 自由記述
        requests.append(
            {
                "createItem": {
                    "item": {
                        "itemId": question_item_id,
                        "title": item.question,
                        "questionItem": {
                            "question": {
                                "required": True,
                                "textQuestion": {"paragraph": True},
                            }
                        },
                    },
                    "location": {"index": index},
                }
            }
        )
        index += 1

        # ページ区切り → セクション2: 模範解答・解説（回答不要の表示アイテム）
        requests.append(
            {
                "createItem": {
                    "item": {
                        "itemId": info_item_id,
                        "title": "模範解答・解説",
                        "description": f"模範解答: {item.model_answer}\n\n解説: {item.explanation}",
                        "pageBreakItem": {},
                    },
                    "location": {"index": index},
                }
            }
        )
        index += 1

        # セクション3: 自己採点
        requests.append(
            {
                "createItem": {
                    "item": {
                        "itemId": grade_item_id,
                        "title": "自己採点してください",
                        "questionItem": {
                            "question": {
                                "required": True,
                                "choiceQuestion": {
                                    "type": "RADIO",
                                    "options": [{"value": option} for option in SELF_GRADE_OPTIONS],
                                    "shuffle": False,
                                },
                            }
                        },
                    },
                    "location": {"index": index},
                }
            }
        )
        index += 1

    return requests, item_map
