"""統計検定準1級 Domain Plugin。

出題範囲4分野をCompetencyとして宣言し、`scripts/toukei_cli.py` が書き込む
`~/.academic-toukei/toukei.db`（`toukei_study.db`、acenglishの`skill_state`と
同じ意味論の最小構成）を読んで mastery を要約する。
"""

from __future__ import annotations

import sqlite3

from .base import CompetencyTemplate, DomainPlugin, MasterySummary, ResourceGapHint

DOMAIN_ID = "toukei"

TOUKEI_COMPETENCIES: tuple[CompetencyTemplate, ...] = (
    CompetencyTemplate(
        competency_id="toukei.probability_distribution",
        domain_id=DOMAIN_ID,
        title="確率と確率分布",
        domain_ref="toukei.probability_distribution",
        exam_weight=0.25,
    ),
    CompetencyTemplate(
        competency_id="toukei.statistical_inference",
        domain_id=DOMAIN_ID,
        title="統計的推測",
        domain_ref="toukei.statistical_inference",
        exam_weight=0.25,
    ),
    CompetencyTemplate(
        competency_id="toukei.multivariate_analysis",
        domain_id=DOMAIN_ID,
        title="多変量解析法",
        domain_ref="toukei.multivariate_analysis",
        exam_weight=0.25,
    ),
    CompetencyTemplate(
        competency_id="toukei.applications",
        domain_id=DOMAIN_ID,
        title="種々の応用",
        domain_ref="toukei.applications",
        exam_weight=0.25,
    ),
)


class ToukeiPlugin(DomainPlugin):
    """`toukei_study` の DB（`toukei.db`）を読んで Core 向けに要約する。"""

    domain_id = DOMAIN_ID

    def __init__(self, toukei_connection: sqlite3.Connection) -> None:
        self._connection = toukei_connection

    def competencies(self) -> list[CompetencyTemplate]:
        return list(TOUKEI_COMPETENCIES)

    def mastery_summary(self, competencies: list[CompetencyTemplate]) -> dict[str, MasterySummary]:
        summaries: dict[str, MasterySummary] = {}
        for competency in competencies:
            summaries[competency.competency_id] = self._summarize_one(competency)
        return summaries

    def _summarize_one(self, competency: CompetencyTemplate) -> MasterySummary:
        row = self._connection.execute(
            "SELECT mastery, confidence, attempts, error_streak, updated_at FROM skill_state"
            " WHERE competency_id = ?",
            (competency.domain_ref,),
        ).fetchone()
        if row is None or row["attempts"] == 0:
            return MasterySummary(competency_id=competency.competency_id, note="attemptが無い")
        return MasterySummary(
            competency_id=competency.competency_id,
            mastery=row["mastery"],
            confidence=row["confidence"],
            attempts=row["attempts"],
            error_streak=row["error_streak"],
            updated_at=row["updated_at"],
        )

    def resource_gap_hint(
        self, competency: CompetencyTemplate, summary: MasterySummary
    ) -> ResourceGapHint | None:
        if summary.attempts == 0:
            return ResourceGapHint(
                competency_id=competency.competency_id,
                gap_kind="volume",
                reason="attemptが0件。問題演習が必要",
            )
        if summary.mastery is not None and summary.mastery < 0.5 and summary.attempts >= 5:
            return ResourceGapHint(
                competency_id=competency.competency_id,
                gap_kind="difficulty",
                reason=f"mastery={summary.mastery:.2f}（attempts={summary.attempts}）が低いまま推移。10日しかないため優先的に演習を増やすべき",
            )
        return None
