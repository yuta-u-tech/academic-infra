"""学習の閉ループ本体。

    出題 → 回答 → 誤答原因の分類 → 学習者モデル更新 → 復習キュー再計算
        → （資料の不足と判定されたら）追記候補を立てる

要件 §14 の一本道はここに集約されている。API も CLI もこの関数を呼ぶだけにして、
経路ごとに挙動がずれないようにする。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .db import now_iso
from .diagnose import ErrorCause, classify, escalate, next_action, open_revision_candidate
from .items import GrammarItem, ListeningItem, ReadingBlankItem, ReadingItem, VocabItem
from .model import AttemptSignals, schedule_review, update_skill_state

_ITEM_TYPES = {
    "vocab": VocabItem,
    "reading": ReadingItem,
    "grammar": GrammarItem,
    "listening": ListeningItem,
    "reading_blank": ReadingBlankItem,
}
# 出題時に隠すフィールド。答えと解説が UI に流れると、正誤の記録が意味をなくなる。
_HIDDEN_FIELDS = {
    # example と collocations/collocations_v2 は見出し語をそのまま含む（"preside over a meeting"）。
    # 語義だけ見て思い出す問題なので、これを出したら答えを見せているのと変わらない。
    # 答え合わせのときに返す。
    "vocab": ("word", "example", "collocations", "collocations_v2"),
    "reading": ("answer_index", "explanation"),
    "grammar": ("answer_index", "explanation"),
    "listening": ("answer_index", "explanation"),
    "reading_blank": ("answer_index", "explanation", "pattern", "pattern_note"),
}
# 外部素材（TOEIC/VOA/TED）には直すべき科目資料が無いので、還元先はノートになる。
_NOTE_SOURCES = {"toeic", "voa", "ted"}


@dataclass(frozen=True)
class AnswerOutcome:
    """1回の回答の結果。UI にそのまま返せる形。"""

    attempt_id: int
    correct: bool
    quality_domain: str
    error_cause: str | None
    next_action: str
    skill_state: dict
    review: dict
    revision_candidate_id: int | None


def start_session(connection: sqlite3.Connection, course_id: str, note: str | None = None) -> int:
    cursor = connection.execute(
        "INSERT INTO learning_session (course_id, started_at, note) VALUES (?, ?, ?)",
        (course_id, now_iso(), note),
    )
    connection.commit()
    return int(cursor.lastrowid)


def end_session(connection: sqlite3.Connection, session_id: int) -> None:
    connection.execute(
        "UPDATE learning_session SET ended_at = ? WHERE id = ?", (now_iso(), session_id)
    )
    connection.commit()


def load_item(connection: sqlite3.Connection, item_id: int) -> tuple[dict, VocabItem | ReadingItem | GrammarItem | ListeningItem | ReadingBlankItem]:
    row = connection.execute("SELECT * FROM generated_item WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise LookupError(f"generated_item {item_id} がありません。")
    model = _ITEM_TYPES[row["kind"]]
    return dict(row), model.model_validate_json(row["payload"])


def answer(
    connection: sqlite3.Connection,
    session_id: int,
    item_id: int,
    response: str,
    elapsed_ms: int,
    self_confidence: float | None = None,
    hint_used: bool = False,
    retry_count: int = 0,
    cause_override: str | None = None,
    correct_override: bool | None = None,
) -> AnswerOutcome:
    """回答を1件記録し、閉ループを最後まで回す。

    correct_override を渡すと item.check(response) を使わず、その真偽値をそのまま
    正誤として扱う。語彙テスト（VocabItem）のように、正解が item 自身ではなく
    出題のたびに変わる選択肢セット（Forms の form_map 側）にしか存在しないケースで使う。
    """
    row, item = load_item(connection, item_id)
    correct = item.check(response) if correct_override is None else correct_override

    signals = AttemptSignals(
        domain=item.domain,
        sub_skill=item.sub_skill,
        target_ref=row["review_id"],
        correct=correct,
        elapsed_ms=elapsed_ms,
        hint_used=hint_used,
        retry_count=retry_count,
        self_confidence=self_confidence,
        days_since_last=_days_since_last(connection, item_id),
    )

    cause = classify(connection, signals, cause_override)

    cursor = connection.execute(
        """
        INSERT INTO attempt (
            session_id, item_id, review_id, domain, sub_skill, response, correct,
            elapsed_ms, self_confidence, hint_used, retry_count, error_cause,
            days_since_last, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            item_id,
            row["review_id"],
            item.domain,
            item.sub_skill,
            response,
            1 if correct else 0,
            elapsed_ms,
            self_confidence,
            1 if hint_used else 0,
            retry_count,
            cause.value if cause else None,
            signals.days_since_last,
            now_iso(),
        ),
    )
    attempt_id = int(cursor.lastrowid)
    connection.commit()

    skill_state = update_skill_state(connection, signals)
    # 答えを見たあとの自己申告で引き直せるよう、進める前の地点を控えておく。
    connection.execute(
        "UPDATE attempt SET queue_state_before = ? WHERE id = ?",
        (json.dumps(_queue_state(connection, item_id)), attempt_id),
    )
    connection.commit()
    review = schedule_review(connection, item_id, row["review_id"], signals)

    candidate_id = None
    if not correct and escalate(connection, row["review_id"], item.domain, item.sub_skill):
        cause = ErrorCause.MATERIAL_GAP
        connection.execute(
            "UPDATE attempt SET error_cause = ? WHERE id = ?", (cause.value, attempt_id)
        )
        connection.commit()
        candidate_id = _open_candidate(connection, row, item, skill_state)

    return AnswerOutcome(
        attempt_id=attempt_id,
        correct=correct,
        quality_domain=item.domain,
        error_cause=cause.value if cause else None,
        next_action=next_action(cause),
        skill_state=skill_state,
        review=review,
        revision_candidate_id=candidate_id,
    )


def find_item_id_by_review_id(connection: sqlite3.Connection, review_id: str) -> int | None:
    """review_id から generated_item.id を引く。

    answer() / load_item() は item_id（自動採番の内部ID）を前提にしているが、
    Google Forms 経由の回答は review_id しか知らない（toeic_forms.builder が
    review_id を鍵にForm設問を組み立てているため）。同じ review_id で複数回
    ingest し直されていても構わないよう、最新（retired_at IS NULL）の1件を返す。
    """
    row = connection.execute(
        "SELECT id FROM generated_item WHERE review_id = ? AND retired_at IS NULL"
        " ORDER BY created_at DESC LIMIT 1",
        (review_id,),
    ).fetchone()
    return int(row["id"]) if row is not None else None


def record_form_response(
    connection: sqlite3.Connection,
    session_id: int,
    review_id: str,
    response: str,
    elapsed_ms: int = 0,
    correct_override: bool | None = None,
) -> AnswerOutcome:
    """Google Forms 経由（選択式）の回答を1件記録する。

    ローカルUI（acenglish serve）のセッションの外から、翌朝バッチが呼ぶ想定。
    採点・誤答分類・復習スケジューリングは answer() とまったく同じロジックを通す
    （経路によって閉ループの中身がずれると学習履歴の意味が変わってしまうため）。

    correct_override は語彙テスト向け（form_map側のanswer_indexで採点する。
    answer() のdocstring参照）。Part5/Part7/リスニングは渡さず、従来通り
    item.check(response) に任せる。

    記述式（自己採点）の回答はここでは扱わない — 自己採点の結果は item.check() が
    比較できる「正解」を持たない（本人の申告そのものが正誤）ため、answer() の
    correct = item.check(response) という前提に乗らない。
    """
    item_id = find_item_id_by_review_id(connection, review_id)
    if item_id is None:
        raise LookupError(f"review_id={review_id} に対応する generated_item が見つかりません。")
    return answer(connection, session_id, item_id, response, elapsed_ms, correct_override=correct_override)


# 答えを見たあとに本人が付ける手応え。Anki の4段階と同じ粒度。
GRADE_CONFIDENCE = {0: 0.0, 1: 0.34, 2: 0.67, 3: 1.0}


def grade(connection: sqlite3.Connection, attempt_id: int, value: int) -> dict:
    """回答後の自己申告。**復習間隔だけ**を動かす。

    mastery は動かさない。正誤・所要時間・ミス回数・ヒントという観測できる事実から
    既に算出してあり、あとから自己申告で上書きすると測っているものが変わる。
    自己申告が効くのは「次にいつ出すか」で、そこは本人の感覚の方が正確
    （「正解したが勘だった」は間隔を伸ばすべきではない）。
    """
    if value not in GRADE_CONFIDENCE:
        raise ValueError(f"grade は {sorted(GRADE_CONFIDENCE)} のいずれかです: {value}")

    row = connection.execute("SELECT * FROM attempt WHERE id = ?", (attempt_id,)).fetchone()
    if row is None:
        raise LookupError(f"attempt {attempt_id} がありません。")

    confidence = GRADE_CONFIDENCE[value]
    connection.execute(
        "UPDATE attempt SET self_confidence = ? WHERE id = ?", (confidence, attempt_id)
    )
    # 回答直後の地点まで巻き戻してから引き直す。巻き戻さずに再計算すると、
    # 1回の回答で SM-2 が2段進んでしまう（1日後 → 6日後）。
    before = json.loads(row["queue_state_before"]) if row["queue_state_before"] else None
    if before is None:
        connection.execute("DELETE FROM review_queue WHERE item_id = ?", (row["item_id"],))
    else:
        connection.execute(
            "UPDATE review_queue SET interval = ?, ease_factor = ?, repetitions = ?"
            " WHERE item_id = ?",
            (before["interval"], before["ease_factor"], before["repetitions"], row["item_id"]),
        )
    connection.commit()

    signals = AttemptSignals(
        domain=row["domain"],
        sub_skill=row["sub_skill"],
        target_ref=row["review_id"],
        # 「もう一度」は、正解していても間隔をリセットする（勘で当てた場合に効く）。
        correct=bool(row["correct"]) and value > 0,
        elapsed_ms=row["elapsed_ms"],
        hint_used=bool(row["hint_used"]),
        retry_count=row["retry_count"],
        self_confidence=confidence,
        days_since_last=row["days_since_last"],
    )
    return schedule_review(connection, row["item_id"], row["review_id"], signals)


def _open_candidate(
    connection: sqlite3.Connection,
    row: dict,
    item: VocabItem | ReadingItem | GrammarItem | ListeningItem | ReadingBlankItem,
    skill_state: dict,
) -> int:
    """繰り返し間違えた箇所について、追記候補を1件立てる。

    行き先は素材によって変わる。科目資料なら「章の説明が足りない」→ 科目リポジトリの
    Issue へ、TOEIC/VOA/TED なら直すべき章が無いので「自分用ノートに書き足す」→
    english-notes の drafts/ へ。どちらも**この時点ではまだ何も書き換えない**。

    問題文・修正仕様は「誤答の事実」から機械的に組み立てられる範囲に留める。
    どう書くかの本文は Claude が Issue化／ノート化の直前に肉付けする前提。
    """
    material = connection.execute(
        "SELECT * FROM material WHERE review_id = ?", (row["review_id"],)
    ).fetchone()
    title = material["title"] if material else row["review_id"]
    source_file = material["source_file"] if material else "(未確定)"
    source = material["source"] if material else "academic"
    is_note = source in _NOTE_SOURCES

    streak = skill_state["error_streak"]
    latency = skill_state["latency_ms_p50"]
    if is_note:
        problem = (
            f"「{title}」（{source}）を {item.domain}/{item.sub_skill} の演習で "
            f"{streak}回連続して間違えている。回答時間の中央値は {latency}ms、"
            f"ヒント使用率は {skill_state['hint_rate']:.0%}。"
            "自分のノートにこの項目の整理が無いか、あっても区別が書けていない。"
        )
        fix_spec = [
            f"{source_file} に「{title}」の項目を追加する（既にあれば書き足す）",
            "間違えた理由（何と取り違えたか）を自分の言葉で書く",
            "自分で作った例文を1つ添える（出典の例文をそのまま写さない）",
        ]
        candidate_title = f"{title}: {streak}回続けて間違えている"
    else:
        problem = (
            f"「{title}」について、{item.domain}/{item.sub_skill} の演習で "
            f"{streak}回連続して誤答している。回答時間の中央値は {latency}ms、"
            f"ヒント使用率は {skill_state['hint_rate']:.0%}。"
            "本人が覚えていないだけでなく、資料側の説明・例が不足している可能性がある。"
        )
        fix_spec = [
            f"{title} の該当箇所に、誤答が集中している論点の説明を追記する",
            "具体例を1つ以上追加する（既存の記号体系は変えない）",
            "英語で説明する際の対応表現を併記する",
        ]
        candidate_title = f"{title} の説明が不足している（英語演習での誤答{streak}回）"

    evidence = {
        "review_id": row["review_id"],
        "source": source,
        "origin": material["origin"] if material else None,
        "domain": item.domain,
        "sub_skill": item.sub_skill,
        "error_streak": streak,
        "mastery": skill_state["mastery"],
        "latency_ms_p50": latency,
        "item_prompt": item.prompt(),
        "source_commit": row["source_commit"],
    }
    return open_revision_candidate(
        connection,
        review_id=row["review_id"],
        course_id=row["course_id"],
        source_file=source_file,
        title=candidate_title,
        problem=problem,
        fix_spec=fix_spec,
        evidence=evidence,
        target_kind="english_note" if is_note else "course_repo",
    )


def _queue_state(connection: sqlite3.Connection, item_id: int) -> dict | None:
    row = connection.execute(
        "SELECT interval, ease_factor, repetitions FROM review_queue WHERE item_id = ?",
        (item_id,),
    ).fetchone()
    return dict(row) if row else None


def _days_since_last(connection: sqlite3.Connection, item_id: int) -> float | None:
    row = connection.execute(
        "SELECT created_at FROM attempt WHERE item_id = ? ORDER BY id DESC LIMIT 1", (item_id,)
    ).fetchone()
    if row is None:
        return None
    previous = datetime.fromisoformat(row["created_at"])
    now = datetime.fromisoformat(now_iso())
    return round((now - previous).total_seconds() / 86_400, 4)


def answer_pattern(word: str) -> str:
    """綴りを伏せたまま、長さと語の区切りだけを見せる形。

    1文字ずつ正誤を返す方式は採らない。総当たりで必ず正解できてしまい、
    「思い出せたか」を測るという目的そのものが壊れるため。
    """
    return "".join(character if character in " -'’" else "·" for character in word)


def hint_for(word: str) -> str:
    """各語の頭文字だけ開ける。"""
    parts = []
    for chunk in word.split(" "):
        parts.append(chunk[:1] + answer_pattern(chunk[1:]) if chunk else chunk)
    return " ".join(parts)


def item_for_ui(connection: sqlite3.Connection, item_id: int) -> dict[str, Any]:
    """出題用。答え（answer_index / word / explanation）は含めない。"""
    row, item = load_item(connection, item_id)
    payload = json.loads(row["payload"])
    hidden_fields = _HIDDEN_FIELDS.get(row["kind"], ())
    if row["kind"] == "vocab" and item.sub_skill == "recognition":
        hidden_fields = ("meaning", "example", "collocations", "collocations_v2")
    elif row["kind"] == "vocab":
        # 綴りは伏せるが、何語で何文字かは打つ前に要る情報なので渡す。
        payload["answer_pattern"] = answer_pattern(item.word)
    for field in hidden_fields:
        payload.pop(field, None)
    return {
        "item_id": item_id,
        "kind": row["kind"],
        "review_id": row["review_id"],
        "course_id": row["course_id"],
        "difficulty": row["difficulty"],
        "domain": item.domain,
        "sub_skill": item.sub_skill,
        "payload": payload,
    }
