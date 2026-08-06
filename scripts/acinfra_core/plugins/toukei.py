"""統計検定準1級 Domain Plugin。

TOEICと違い、統計検定向けの問題生成・attempt記録の仕組み（acenglish相当）は
まだ存在しない。ここでは公式の出題範囲4分野をCompetencyとして宣言するだけに
留め、`domain_ref=None` のまま「未接続」を正直に返す（`toeic.py` の Part7 と
同じパターン）。生成器・attempt記録の仕組みができたら `domain_ref` を埋める。
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
        domain_ref=None,
        exam_weight=0.25,
    ),
    CompetencyTemplate(
        competency_id="toukei.statistical_inference",
        domain_id=DOMAIN_ID,
        title="統計的推測",
        domain_ref=None,
        exam_weight=0.25,
    ),
    CompetencyTemplate(
        competency_id="toukei.multivariate_analysis",
        domain_id=DOMAIN_ID,
        title="多変量解析法",
        domain_ref=None,
        exam_weight=0.25,
    ),
    CompetencyTemplate(
        competency_id="toukei.applications",
        domain_id=DOMAIN_ID,
        title="種々の応用",
        domain_ref=None,
        exam_weight=0.25,
    ),
)


class ToukeiPlugin(DomainPlugin):
    """生成器・attempt記録が未実装のため、常に「未接続」を返すプレースホルダ。"""

    domain_id = DOMAIN_ID

    def __init__(self, acenglish_connection: sqlite3.Connection) -> None:
        # CLI側の呼び出し規約に合わせているだけで、現状は使わない。
        self._connection = acenglish_connection

    def competencies(self) -> list[CompetencyTemplate]:
        return list(TOUKEI_COMPETENCIES)

    def mastery_summary(self, competencies: list[CompetencyTemplate]) -> dict[str, MasterySummary]:
        return {
            competency.competency_id: MasterySummary(
                competency_id=competency.competency_id,
                note="attempt記録の仕組み未実装（生成器がまだ無い）",
            )
            for competency in competencies
        }

    def resource_gap_hint(
        self, competency: CompetencyTemplate, summary: MasterySummary
    ) -> ResourceGapHint | None:
        return ResourceGapHint(
            competency_id=competency.competency_id,
            gap_kind="coverage",
            reason="学習ループに未接続（この Competency 向けの生成器/取り込みがまだ無い）",
        )
