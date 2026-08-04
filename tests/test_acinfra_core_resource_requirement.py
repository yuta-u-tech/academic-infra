import pytest

from acinfra_core import goal, resource_requirement as rr
from acinfra_core.db import connect
from acinfra_core.plugins.base import ResourceGapHint


@pytest.fixture
def connection(tmp_path):
    with connect(tmp_path / "core.db") as conn:
        goal.create_goal(conn, "toeic-900", "TOEIC 900点")
        yield conn


def test_open_requirement_round_trips(connection):
    created = rr.open_requirement(
        connection, "toeic-900", "req-1",
        competency_ids=["toeic.vocabulary.recall"],
        gap_kind="volume",
        priority="high",
        spec={"reason": "attemptが0件"},
    )
    assert created.status == "unresolved"
    assert created.competency_ids == ["toeic.vocabulary.recall"]

    fetched = rr.get_requirement(connection, "req-1")
    assert fetched == created


def test_open_requirement_requires_existing_goal(connection):
    with pytest.raises(goal.GoalNotFoundError):
        rr.open_requirement(
            connection, "no-such-goal", "req-1",
            competency_ids=[], gap_kind="volume", priority="low", spec={},
        )


def test_open_requirement_rejects_unknown_gap_kind(connection):
    with pytest.raises(rr.InvalidResourceRequirementError):
        rr.open_requirement(
            connection, "toeic-900", "req-1",
            competency_ids=[], gap_kind="not-a-gap-kind", priority="low", spec={},
        )


def test_open_requirement_rejects_unknown_priority(connection):
    with pytest.raises(rr.InvalidResourceRequirementError):
        rr.open_requirement(
            connection, "toeic-900", "req-1",
            competency_ids=[], gap_kind="volume", priority="not-a-priority", spec={},
        )


def test_open_requirement_rejects_duplicate_id(connection):
    rr.open_requirement(
        connection, "toeic-900", "req-1",
        competency_ids=[], gap_kind="volume", priority="low", spec={},
    )
    with pytest.raises(rr.DuplicateResourceRequirementError):
        rr.open_requirement(
            connection, "toeic-900", "req-1",
            competency_ids=[], gap_kind="volume", priority="low", spec={},
        )


def test_open_requirement_from_gap_hint(connection):
    hint = ResourceGapHint(
        competency_id="toeic.vocabulary.recall", gap_kind="difficulty", reason="masteryが低い",
    )
    created = rr.open_requirement_from_gap_hint(connection, "toeic-900", "req-1", hint)
    assert created.gap_kind == "difficulty"
    assert created.competency_ids == ["toeic.vocabulary.recall"]


def test_list_requirements_filters_by_status(connection):
    rr.open_requirement(connection, "toeic-900", "req-1", competency_ids=[], gap_kind="volume", priority="low", spec={})
    rr.open_requirement(connection, "toeic-900", "req-2", competency_ids=[], gap_kind="volume", priority="low", spec={})
    rr.update_requirement_status(connection, "req-2", "resolved")

    assert [r.requirement_id for r in rr.list_requirements(connection, "toeic-900", status="unresolved")] == ["req-1"]
    assert [r.requirement_id for r in rr.list_requirements(connection, "toeic-900", status="resolved")] == ["req-2"]


def test_update_requirement_status_rejects_unknown_status(connection):
    rr.open_requirement(connection, "toeic-900", "req-1", competency_ids=[], gap_kind="volume", priority="low", spec={})
    with pytest.raises(rr.InvalidResourceRequirementError):
        rr.update_requirement_status(connection, "req-1", "not-a-status")


def test_update_requirement_status_requires_existing_requirement(connection):
    with pytest.raises(rr.ResourceRequirementNotFoundError):
        rr.update_requirement_status(connection, "no-such-req", "resolved")
