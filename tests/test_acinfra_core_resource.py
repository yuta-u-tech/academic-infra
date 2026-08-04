import pytest

from acinfra_core import goal, resource
from acinfra_core.db import connect


@pytest.fixture
def connection(tmp_path):
    with connect(tmp_path / "core.db") as conn:
        goal.create_goal(conn, "toeic-900", "TOEIC 900点")
        yield conn


def test_register_resource_round_trips(connection):
    created = resource.register_resource(
        connection, "toeic-900", "official-toeic-vol8", "TOEIC公式問題集8", "book",
        authority="official",
    )
    assert created.status == "candidate"

    fetched = resource.get_resource(connection, "official-toeic-vol8")
    assert fetched == created


def test_register_resource_requires_existing_goal(connection):
    with pytest.raises(goal.GoalNotFoundError):
        resource.register_resource(connection, "no-such-goal", "r1", "title", "book")


def test_register_resource_rejects_duplicate_id(connection):
    resource.register_resource(connection, "toeic-900", "r1", "A", "book")
    with pytest.raises(resource.DuplicateResourceError):
        resource.register_resource(connection, "toeic-900", "r1", "B", "book")


def test_register_resource_rejects_unknown_status(connection):
    with pytest.raises(resource.InvalidResourceStatusError):
        resource.register_resource(connection, "toeic-900", "r1", "A", "book", status="not-a-status")


def test_get_resource_raises_when_missing(connection):
    with pytest.raises(resource.ResourceNotFoundError):
        resource.get_resource(connection, "no-such-resource")


def test_list_resources_filters_by_status(connection):
    resource.register_resource(connection, "toeic-900", "r1", "A", "book")
    resource.register_resource(connection, "toeic-900", "r2", "B", "book")
    resource.update_resource_status(connection, "r2", "active")

    assert [r.resource_id for r in resource.list_resources(connection, "toeic-900", status="candidate")] == ["r1"]
    assert [r.resource_id for r in resource.list_resources(connection, "toeic-900", status="active")] == ["r2"]
    assert {r.resource_id for r in resource.list_resources(connection, "toeic-900")} == {"r1", "r2"}


def test_update_resource_status_rejects_unknown_status(connection):
    resource.register_resource(connection, "toeic-900", "r1", "A", "book")
    with pytest.raises(resource.InvalidResourceStatusError):
        resource.update_resource_status(connection, "r1", "not-a-status")
