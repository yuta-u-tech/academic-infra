"""TOEIC Domain Plugin。`acenglish` を作り直さず、Core Interface に接続するだけ。

設計: docs/2026-08-04-goal-driven-learning-platform.md §7

`attempt` が実際に貯まるのは TOEIC 語彙（`acenglish.sources.studyforge`）と
Part5 文法（`acenglish.sources.toeic_part5`、`toeic_reading_cli.py ingest` 経由）の
2つ。Part7 読解はまだ `toeic_reading` 側に生成器が無く学習ループに未接続なので、
ここでは `domain_ref=None` のまま宣言し、`mastery_summary()` は正直に「データなし」を
返す。Part7用の生成器ができてから埋める（別Issue）。
"""

from __future__ import annotations

import json
import sqlite3

from .base import CompetencyTemplate, DomainPlugin, MasterySummary, ResourceGapHint

DOMAIN_ID = "toeic"

# target_ref_prefix は各 acenglish.sources.* が振る review_id の接頭辞に対応する。
# deck/セット単位に分けないのは、TOEIC語彙・Part5文法という粒度で mastery を見たいため
# （内訳が要るようになったら分割する）。
_VOCAB_REF = json.dumps({"acenglish_domain": "vocabulary", "sub_skill": "recall", "target_ref_prefix": "toeic."})
# GrammarItem.sub_skill の既定値（"knowledge"）に合わせる。items.json 側で明示的に
# 別の sub_skill（processing_speed 等）を指定した問題はこの集計に含まれない。
_PART5_REF = json.dumps(
    {"acenglish_domain": "grammar", "sub_skill": "knowledge", "target_ref_prefix": "toeic.part5."}
)

TOEIC_COMPETENCIES: tuple[CompetencyTemplate, ...] = (
    CompetencyTemplate(
        competency_id="toeic.vocabulary.recall",
        domain_id=DOMAIN_ID,
        title="TOEIC語彙（再生）",
        domain_ref=_VOCAB_REF,
        exam_weight=0.3,
    ),
    CompetencyTemplate(
        competency_id="toeic.part5.grammar",
        domain_id=DOMAIN_ID,
        title="Part5 文法（短文穴埋め）",
        domain_ref=_PART5_REF,
        exam_weight=0.2,
    ),
    CompetencyTemplate(
        competency_id="toeic.part7.reading",
        domain_id=DOMAIN_ID,
        title="Part7 読解（長文）",
        domain_ref=None,
        exam_weight=0.3,
    ),
)


class ToeicPlugin(DomainPlugin):
    """`acenglish` の DB（`english.db`）を読んで Core 向けに要約する。"""

    domain_id = DOMAIN_ID

    def __init__(self, acenglish_connection: sqlite3.Connection) -> None:
        self._connection = acenglish_connection

    def competencies(self) -> list[CompetencyTemplate]:
        return list(TOEIC_COMPETENCIES)

    def mastery_summary(self, competencies: list[CompetencyTemplate]) -> dict[str, MasterySummary]:
        summaries: dict[str, MasterySummary] = {}
        for competency in competencies:
            summaries[competency.competency_id] = self._summarize_one(competency)
        return summaries

    def _summarize_one(self, competency: CompetencyTemplate) -> MasterySummary:
        if competency.domain_ref is None:
            return MasterySummary(
                competency_id=competency.competency_id,
                note="acenglish未接続（この Competency 向けの生成器/取り込みがまだ無い）",
            )
        spec = json.loads(competency.domain_ref)
        rows = self._connection.execute(
            "SELECT mastery, confidence, attempts, error_streak, updated_at FROM skill_state"
            " WHERE domain = ? AND sub_skill = ? AND target_ref LIKE ?",
            (spec["acenglish_domain"], spec["sub_skill"], f"{spec['target_ref_prefix']}%"),
        ).fetchall()
        if not rows:
            return MasterySummary(competency_id=competency.competency_id, note="attemptが無い")

        total_attempts = sum(row["attempts"] for row in rows)
        if total_attempts == 0:
            return MasterySummary(competency_id=competency.competency_id, note="attemptが無い")

        # target_ref（単語ごと）にまたがる集計なので、単純平均ではなく attempts で重み付けする。
        weighted_mastery = sum(row["mastery"] * row["attempts"] for row in rows) / total_attempts
        weighted_confidence = sum(row["confidence"] * row["attempts"] for row in rows) / total_attempts
        return MasterySummary(
            competency_id=competency.competency_id,
            mastery=round(weighted_mastery, 4),
            confidence=round(weighted_confidence, 4),
            attempts=total_attempts,
            error_streak=max(row["error_streak"] for row in rows),
            updated_at=max(row["updated_at"] for row in rows),
        )

    def resource_gap_hint(
        self, competency: CompetencyTemplate, summary: MasterySummary
    ) -> ResourceGapHint | None:
        if competency.domain_ref is None:
            return ResourceGapHint(
                competency_id=competency.competency_id,
                gap_kind="coverage",
                reason="学習ループに未接続（この Competency 向けの生成器/取り込みがまだ無い）",
            )
        if summary.attempts == 0:
            return ResourceGapHint(
                competency_id=competency.competency_id,
                gap_kind="volume",
                reason="attemptが0件。教材の取り込みまたは学習セッションが必要",
            )
        if summary.mastery is not None and summary.mastery < 0.4 and summary.attempts >= 5:
            return ResourceGapHint(
                competency_id=competency.competency_id,
                gap_kind="difficulty",
                reason=f"mastery={summary.mastery:.2f}（attempts={summary.attempts}）が低いまま推移",
            )
        return None
