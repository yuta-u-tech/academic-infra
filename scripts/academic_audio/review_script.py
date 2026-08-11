"""間違えたTOEIC問題から復習動画の台本(DialogueScript)を組み立てる。

「なぜその答えなのか」を短い英語のreasonにまとめるのは機械的には書けない判断なので、
Claudeが1問ずつ書く（`generate.py` の request/ingest と同じ役割分担 — ここは器だけ）。
入力は `{review_id, sentence, choices, answer_index, reason}` の配列で、
`acenglish.toeic_review.fetch_wrong_items()` が返す誤答データに reason を足した形。
"""

from __future__ import annotations

from academic_audio.models import DialogueScript, DialogueSegment

_LETTERS = "ABCDEF"


class ReviewItemError(ValueError):
    pass


def _validate(item: dict, index: int) -> None:
    missing = [key for key in ("review_id", "sentence", "choices", "answer_index", "reason") if key not in item]
    if missing:
        raise ReviewItemError(f"items[{index}] に {', '.join(missing)} がありません。")
    if not (0 <= item["answer_index"] < len(item["choices"])):
        raise ReviewItemError(f"items[{index}]: answer_index が choices の範囲外です。")


def build_review_script(title: str, source_id: str, items: list[dict]) -> DialogueScript:
    if not items:
        raise ReviewItemError("items が空です。")

    segments: list[DialogueSegment] = [
        DialogueSegment(
            id="intro", speaker="narrator", language="en", pause=1.0,
            text=f"{title}. Let's review the questions you got wrong.",
        )
    ]

    for index, item in enumerate(items, start=1):
        _validate(item, index)
        review_id = item["review_id"]
        choices = item["choices"]
        answer_index = item["answer_index"]
        letter = _LETTERS[answer_index]
        answer = choices[answer_index]
        sentence = item["sentence"].replace("____", "blank")
        choice_text = " ".join(f"{_LETTERS[j]}, {choice}." for j, choice in enumerate(choices))

        segments.append(DialogueSegment(
            id=f"{review_id}.question", speaker="narrator", language="en", pause=1.0,
            item_id=review_id, role="question", text=f"Question {index}. {sentence}",
        ))
        segments.append(DialogueSegment(
            id=f"{review_id}.choices", speaker="narrator", language="en", pause=2.5,
            item_id=review_id, role="choices", text=choice_text,
        ))
        segments.append(DialogueSegment(
            id=f"{review_id}.answer", speaker="narrator", language="en", pause=0.6,
            item_id=review_id, role="answer", text=f"The answer is {letter}, {answer}.",
        ))
        segments.append(DialogueSegment(
            id=f"{review_id}.reason", speaker="narrator", language="en", pause=1.5,
            item_id=review_id, role="explanation", text=item["reason"],
        ))

    segments.append(DialogueSegment(
        id="outro", speaker="narrator", language="en", pause=0.5,
        text="That's all for today's review. See you next time.",
    ))

    return DialogueScript(title=title, source_id=source_id, source_commit="review", segments=segments)
