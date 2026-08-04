import pytest

from acinfra_core import goal
from acinfra_core.db import connect


@pytest.fixture
def connection(tmp_path):
    with connect(tmp_path / "core.db") as conn:
        yield conn


def test_create_goal_round_trips(connection):
    created = goal.create_goal(connection, "toeic-900", "TOEIC 900点", target_value="900", priority=1)
    assert created.goal_id == "toeic-900"
    assert created.status == "active"

    fetched = goal.get_goal(connection, "toeic-900")
    assert fetched == created


def test_create_goal_rejects_duplicate_id(connection):
    goal.create_goal(connection, "toeic-900", "TOEIC 900点")
    with pytest.raises(goal.DuplicateGoalError):
        goal.create_goal(connection, "toeic-900", "重複")


def test_create_goal_requires_existing_parent(connection):
    with pytest.raises(goal.GoalNotFoundError):
        goal.create_goal(connection, "toeic-900", "TOEIC 900点", parent_goal_id="grad-school")


def test_create_goal_accepts_existing_parent(connection):
    goal.create_goal(connection, "grad-school", "大学院試験合格")
    child = goal.create_goal(connection, "toeic-900", "TOEIC 900点", parent_goal_id="grad-school")
    assert child.parent_goal_id == "grad-school"


def test_get_goal_raises_when_missing(connection):
    with pytest.raises(goal.GoalNotFoundError):
        goal.get_goal(connection, "no-such-goal")


def test_get_goal_returns_none_when_not_required(connection):
    assert goal.get_goal(connection, "no-such-goal", required=False) is None


def test_list_goals_filters_by_status(connection):
    goal.create_goal(connection, "a", "A")
    goal.create_goal(connection, "b", "B")
    goal.update_goal_status(connection, "b", "paused")

    assert [g.goal_id for g in goal.list_goals(connection, status="active")] == ["a"]
    assert [g.goal_id for g in goal.list_goals(connection, status="paused")] == ["b"]
    assert {g.goal_id for g in goal.list_goals(connection)} == {"a", "b"}


def test_update_goal_status_rejects_unknown_status(connection):
    goal.create_goal(connection, "toeic-900", "TOEIC 900点")
    with pytest.raises(goal.InvalidGoalStatusError):
        goal.update_goal_status(connection, "toeic-900", "not-a-real-status")


def test_update_goal_status_requires_existing_goal(connection):
    with pytest.raises(goal.GoalNotFoundError):
        goal.update_goal_status(connection, "no-such-goal", "paused")
