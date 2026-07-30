"""ローカルAPI。認証を持たないので、バインド先の制約をテストで固定する。"""

import pytest
from fastapi.testclient import TestClient

from acenglish import generate
from acenglish.api import DEFAULT_HOST, NonLoopbackBindError, create_app, ensure_loopback
from acenglish.db import connect
from tests.test_english_loop import TARGET, _result


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.10", "10.0.0.1"])
def test_non_loopback_binds_are_refused(host):
    """0.0.0.0 で立てると認証なしの学習データが LAN に出る。設定ミスで済ませない。"""
    with pytest.raises(NonLoopbackBindError):
        ensure_loopback(host)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "127.0.0.2", "localhost"])
def test_loopback_binds_are_allowed(host):
    assert ensure_loopback(host) == host


def test_the_default_host_is_loopback():
    assert ensure_loopback(DEFAULT_HOST) == "127.0.0.1"


def test_a_hostname_is_refused_rather_than_resolved():
    """名前解決に頼ると、その名前が何を指すかで挙動が変わる。"""
    with pytest.raises(NonLoopbackBindError):
        ensure_loopback("example.com")


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "english.db"
    connection = connect(db_path)
    generate.upsert_material(connection, TARGET)
    generate.ingest(connection, _result())
    connection.close()
    return TestClient(create_app(db_path))


def test_health_reports_the_schema_version(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["schema_version"] >= 1


def test_courses_come_from_the_existing_courses_yml(client):
    ids = {c["course_id"] for c in client.get("/api/courses").json()["courses"]}
    assert {"dsa", "statistics", "logic"} <= ids


def test_the_queue_serves_unanswered_items_without_answers(client):
    items = client.get("/api/queue?course=dsa").json()["items"]
    assert len(items) == 2
    reading = next(i for i in items if i["kind"] == "reading")
    assert "answer_index" not in reading["payload"]


def test_answering_returns_the_verdict_and_the_next_interval(client):
    session_id = client.post("/api/sessions", json={"course_id": "dsa"}).json()["session_id"]
    items = client.get("/api/queue?course=dsa").json()["items"]
    vocab = next(i for i in items if i["kind"] == "vocab")

    body = client.post(
        "/api/answer",
        json={
            "session_id": session_id,
            "item_id": vocab["item_id"],
            "response": "linked list",
            "elapsed_ms": 1500,
            "self_confidence": 0.75,
        },
    ).json()

    assert body["correct"] is True
    assert body["answer"] == "linked list"
    assert body["interval_days"] == 1
    assert body["mastery"] > 0


def test_a_wrong_answer_returns_the_explanation(client):
    session_id = client.post("/api/sessions", json={"course_id": "dsa"}).json()["session_id"]
    items = client.get("/api/queue?course=dsa").json()["items"]
    reading = next(i for i in items if i["kind"] == "reading")

    body = client.post(
        "/api/answer",
        json={
            "session_id": session_id,
            "item_id": reading["item_id"],
            "response": "1",
            "elapsed_ms": 8000,
        },
    ).json()

    assert body["correct"] is False
    assert "node" in body["explanation"]
    assert body["error_cause"] == "knowledge_gap"


def test_answering_a_missing_item_is_a_404(client):
    session_id = client.post("/api/sessions", json={"course_id": "dsa"}).json()["session_id"]
    response = client.post(
        "/api/answer",
        json={"session_id": session_id, "item_id": 9999, "response": "x", "elapsed_ms": 100},
    )
    assert response.status_code == 404


def test_confidence_outside_zero_to_one_is_rejected(client):
    response = client.post(
        "/api/answer",
        json={"session_id": 1, "item_id": 1, "response": "x", "elapsed_ms": 10,
              "self_confidence": 5.0},
    )
    assert response.status_code == 422


def test_repeated_failures_surface_a_revision_candidate_through_the_api(client):
    session_id = client.post("/api/sessions", json={"course_id": "dsa"}).json()["session_id"]
    vocab = next(i for i in client.get("/api/queue?course=dsa").json()["items"]
                 if i["kind"] == "vocab")

    for _ in range(3):
        body = client.post(
            "/api/answer",
            json={"session_id": session_id, "item_id": vocab["item_id"],
                  "response": "wrong", "elapsed_ms": 4000},
        ).json()

    assert body["revision_candidate_id"] is not None
    assert client.get("/api/candidates?course=dsa").json()["candidates"]


def test_the_ui_is_served_at_the_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Academic-Infra English" in response.text
