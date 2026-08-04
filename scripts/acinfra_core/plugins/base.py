"""Domain Plugin Interface（設計書 §2.3 の最小形）。

Core は Evidence/Mastery の正規データを持たない。Domain Plugin（例:
`acinfra_core.plugins.toeic`）が自分の DB（`~/.academic-english/english.db` 等）を
持ったまま、Core にはこの Protocol 経由で集計値だけを返す。
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class CompetencyTemplate(BaseModel):
    """Domain Plugin が宣言する Competency の雛形（`goal_id` 未確定の状態）。

    `competency.py` の `register_domain_competencies()` が Goal に紐付けて
    Core の `competency` テーブルへ書き込む。
    """

    competency_id: str
    domain_id: str
    parent_competency_id: str | None = None
    title: str
    domain_ref: str | None = None
    exam_weight: float | None = None


class MasterySummary(BaseModel):
    """Domain Plugin 側の Evidence/Mastery を Core 向けに要約した値。読み取り専用。"""

    competency_id: str
    mastery: float | None = None
    confidence: float | None = None
    attempts: int = 0
    error_streak: int = 0
    updated_at: str | None = None
    note: str | None = None


class ResourceGapHint(BaseModel):
    competency_id: str
    gap_kind: str
    reason: str


class DomainPlugin(Protocol):
    domain_id: str

    def competencies(self) -> list[CompetencyTemplate]: ...

    def mastery_summary(self, competencies: list[CompetencyTemplate]) -> dict[str, MasterySummary]: ...

    def resource_gap_hint(
        self, competency: CompetencyTemplate, summary: MasterySummary
    ) -> ResourceGapHint | None: ...
