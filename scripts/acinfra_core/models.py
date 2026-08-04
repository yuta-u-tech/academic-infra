"""Core のデータモデル。`db.py` の DDL（設計書 §3）に対応する Pydantic モデル。

Evidence/Mastery（`attempt` / `skill_state` 等）はここに含まない。
Domain Plugin（例: `acenglish`）側の型のまま扱う。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

GOAL_STATUSES = ("active", "paused", "achieved", "abandoned")
RESOURCE_STATUSES = ("candidate", "reviewed", "active", "deprecated", "archived")
RESOURCE_REQUIREMENT_STATUSES = ("unresolved", "resolved", "dismissed")
# gap_kind は設計書 §3 の resource_requirement コメント（coverage/difficulty/activity/
# quality/evidence/volume/freshness）をそのまま踏襲する。
RESOURCE_REQUIREMENT_GAP_KINDS = (
    "coverage",
    "difficulty",
    "activity",
    "quality",
    "evidence",
    "volume",
    "freshness",
)
RESOURCE_REQUIREMENT_PRIORITIES = ("low", "medium", "high", "critical")
RESEARCH_REQUEST_STATUSES = ("open", "in_progress", "done", "dismissed")
PROPOSAL_TIERS = ("auto", "suggest", "approval_required")
PROPOSAL_STATUSES = ("pending", "approved", "rejected", "expired")


class Goal(BaseModel):
    goal_id: str
    parent_goal_id: str | None = None
    title: str
    target_value: str | None = None
    current_value: str | None = None
    deadline: str | None = None
    priority: int = 3
    evaluation_method: str | None = None
    status: str = "active"
    created_at: str
    updated_at: str


class Competency(BaseModel):
    competency_id: str
    goal_id: str
    domain_id: str
    parent_competency_id: str | None = None
    title: str
    domain_ref: str | None = None
    exam_weight: float | None = None
    created_at: str


class Resource(BaseModel):
    resource_id: str
    goal_id: str
    title: str
    kind: str
    location: str | None = None
    status: str = "candidate"
    authority: str | None = None
    created_at: str
    updated_at: str


class ResourceRequirement(BaseModel):
    requirement_id: str
    goal_id: str
    competency_ids: list[str] = Field(default_factory=list)
    gap_kind: str
    priority: str
    status: str = "unresolved"
    spec: str
    created_at: str


class ResearchRequest(BaseModel):
    request_id: str
    goal_id: str
    kind: str
    trigger: str
    status: str = "open"
    created_at: str


class Finding(BaseModel):
    finding_id: str
    request_id: str
    summary: str
    proposal_kind: str
    payload: str
    created_at: str


class Proposal(BaseModel):
    proposal_id: str
    goal_id: str
    tier: str
    kind: str
    payload: str
    status: str = "pending"
    reason: str | None = None
    approved_by: str | None = None
    approved_at: str | None = None
    created_at: str


class Intervention(BaseModel):
    intervention_id: str
    goal_id: str
    proposal_id: str | None = None
    change_summary: str
    reason: str
    evidence_ref: str | None = None
    approved_by: str | None = None
    expected_effect: str | None = None
    actual_effect: str | None = None
    confidence: str
    created_at: str
