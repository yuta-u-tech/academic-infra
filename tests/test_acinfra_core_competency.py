import pytest

from acinfra_core import competency, goal
from acinfra_core.db import connect
from acinfra_core.plugins.toeic import TOEIC_COMPETENCIES, ToeicPlugin


@pytest.fixture
def connection(tmp_path):
    with connect(tmp_path / "core.db") as conn:
        yield conn


def test_register_domain_competencies_requires_existing_goal(connection):
    plugin = ToeicPlugin(acenglish_connection=None)
    with pytest.raises(goal.GoalNotFoundError):
        competency.register_domain_competencies(connection, "no-such-goal", plugin)


def test_register_domain_competencies_inserts_the_full_taxonomy(connection):
    goal.create_goal(connection, "toeic-900", "TOEIC 900点")
    plugin = ToeicPlugin(acenglish_connection=None)

    registered = competency.register_domain_competencies(connection, "toeic-900", plugin)

    assert {c.competency_id for c in registered} == {c.competency_id for c in TOEIC_COMPETENCIES}
    assert all(c.goal_id == "toeic-900" for c in registered)


def test_register_domain_competencies_is_idempotent(connection):
    goal.create_goal(connection, "toeic-900", "TOEIC 900点")
    plugin = ToeicPlugin(acenglish_connection=None)

    competency.register_domain_competencies(connection, "toeic-900", plugin)
    second = competency.register_domain_competencies(connection, "toeic-900", plugin)

    assert len(second) == len(TOEIC_COMPETENCIES)


def test_list_competencies_returns_empty_for_goal_without_competencies(connection):
    goal.create_goal(connection, "toeic-900", "TOEIC 900点")
    assert competency.list_competencies(connection, "toeic-900") == []
