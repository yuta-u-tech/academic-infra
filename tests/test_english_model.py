"""学習者モデル: mastery を単純な正答率で表さないことの確認。"""

import pytest

from acenglish.db import connect
from acenglish.model import (
    AttemptSignals,
    due_items,
    next_mastery,
    quality_to_grade,
    response_quality,
    schedule_review,
    sm2,
    update_skill_state,
)


def signals(**overrides) -> AttemptSignals:
    base = dict(
        domain="vocabulary",
        sub_skill="recall",
        target_ref="dsa.ch02.list.s01",
        correct=True,
        elapsed_ms=2_000,
    )
    base.update(overrides)
    return AttemptSignals(**base)


def test_incorrect_answer_has_zero_quality():
    assert response_quality(signals(correct=False)) == 0.0


def test_correct_but_slow_scores_lower_than_correct_and_fast():
    fast = response_quality(signals(elapsed_ms=2_000))
    slow = response_quality(signals(elapsed_ms=30_000))
    assert slow < fast == 1.0


def test_hint_and_retry_discount_a_correct_answer():
    assert response_quality(signals(hint_used=True)) == 0.5
    assert response_quality(signals(retry_count=1)) == 0.5


def test_low_confidence_discounts_but_does_not_erase():
    low = response_quality(signals(self_confidence=0.0))
    high = response_quality(signals(self_confidence=1.0))
    assert 0.0 < low < high == 1.0


def test_slow_answer_is_floored_so_a_correct_answer_still_counts():
    """どれだけ遅くても正答は 0.5 を下回らない（誤答と同じ扱いにしない）。"""
    assert response_quality(signals(elapsed_ms=10_000_000)) == 0.5


def test_mastery_moves_toward_quality_and_slows_with_experience():
    assert next_mastery(0.0, 1.0, attempts=0) > next_mastery(0.0, 1.0, attempts=50)


def test_incorrect_answers_cannot_reach_a_passing_sm2_grade():
    assert quality_to_grade(0.0, correct=False) < 3
    assert quality_to_grade(1.0, correct=True) == 5


def test_sm2_matches_the_goigoi_schedule():
    interval, ease, reps = sm2(0, 2.5, 0, grade=5)
    assert (interval, reps) == (1, 1)
    interval, ease, reps = sm2(interval, ease, reps, grade=5)
    assert (interval, reps) == (6, 2)
    interval, ease, reps = sm2(interval, ease, reps, grade=5)
    assert interval > 6 and reps == 3


def test_sm2_resets_the_interval_on_failure():
    interval, ease, reps = sm2(30, 2.5, 5, grade=1)
    assert (interval, reps) == (1, 0)
    assert ease < 2.5


def test_ease_factor_never_drops_below_the_floor():
    ease = 2.5
    for _ in range(20):
        _, ease, _ = sm2(1, ease, 0, grade=0)
    assert ease == pytest.approx(1.3)


def test_update_skill_state_tracks_streak_and_hint_rate(tmp_path):
    with connect(tmp_path / "e.db") as connection:
        state = update_skill_state(connection, signals(correct=False))
        assert state["error_streak"] == 1
        assert state["mastery"] == 0.0

        state = update_skill_state(connection, signals(correct=False, hint_used=True))
        assert state["error_streak"] == 2
        assert state["hint_rate"] == 0.5

        state = update_skill_state(connection, signals(correct=True))
        assert state["error_streak"] == 0
        assert state["mastery"] > 0.0
        assert state["attempts"] == 3


def test_retention_days_keeps_the_longest_successful_gap(tmp_path):
    with connect(tmp_path / "e.db") as connection:
        update_skill_state(connection, signals(days_since_last=10.0))
        state = update_skill_state(connection, signals(days_since_last=3.0))
        assert state["retention_days"] == 10.0


def _seed_item(connection, item_id: int = 1) -> None:
    connection.execute(
        "INSERT INTO material (review_id, course_id, title, source_file, section_file,"
        " source_commit, updated_at) VALUES ('dsa.ch02.list.s01', 'dsa', 'リスト',"
        " 'src/chapters/ch02.tex', 'sections/ch02-01.md', 'abc123', '2026-07-30T00:00:00+00:00')"
    )
    connection.execute(
        "INSERT INTO generated_item (id, kind, review_id, course_id, payload, difficulty, reason,"
        " generated_by, prompt_version, source_commit, created_at)"
        " VALUES (?, 'vocab', 'dsa.ch02.list.s01', 'dsa', '{}', 2, 'test', 'claude',"
        " '2026-07-30.1', 'abc123', '2026-07-30T00:00:00+00:00')",
        (item_id,),
    )
    connection.commit()


def test_schedule_review_advances_the_queue(tmp_path):
    with connect(tmp_path / "e.db") as connection:
        _seed_item(connection)
        first = schedule_review(connection, 1, "dsa.ch02.list.s01", signals())
        assert first["interval"] == 1 and first["repetitions"] == 1
        second = schedule_review(connection, 1, "dsa.ch02.list.s01", signals())
        assert second["interval"] == 6


def test_due_items_puts_unseen_items_first(tmp_path):
    with connect(tmp_path / "e.db") as connection:
        _seed_item(connection, 1)
        _seed_item_extra(connection, 2)
        schedule_review(connection, 1, "dsa.ch02.list.s01", signals())
        due = due_items(connection, "dsa")
        assert [row["id"] for row in due] == [2]


def _seed_item_extra(connection, item_id: int) -> None:
    connection.execute(
        "INSERT INTO generated_item (id, kind, review_id, course_id, payload, difficulty, reason,"
        " generated_by, prompt_version, source_commit, created_at)"
        " VALUES (?, 'vocab', 'dsa.ch02.list.s01', 'dsa', '{}', 2, 'test', 'claude',"
        " '2026-07-30.1', 'abc123', '2026-07-30T00:00:00+00:00')",
        (item_id,),
    )
    connection.commit()
