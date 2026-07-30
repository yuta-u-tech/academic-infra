"""誤答原因の分類と、資料不足への昇格判定。"""

from acenglish.db import connect
from acenglish.diagnose import ErrorCause, classify, escalate, next_action, open_revision_candidate
from acenglish.model import AttemptSignals, update_skill_state

REVIEW_ID = "dsa.ch02.list.s01"


def signals(**overrides) -> AttemptSignals:
    base = dict(
        domain="vocabulary",
        sub_skill="recall",
        target_ref=REVIEW_ID,
        correct=False,
        elapsed_ms=3_000,
    )
    base.update(overrides)
    return AttemptSignals(**base)


def test_a_fast_correct_answer_has_no_cause(tmp_path):
    with connect(tmp_path / "e.db") as connection:
        assert classify(connection, signals(correct=True, elapsed_ms=1_000)) is None


def test_a_very_slow_correct_answer_is_a_speed_gap(tmp_path):
    with connect(tmp_path / "e.db") as connection:
        assert classify(connection, signals(correct=True, elapsed_ms=60_000)) is ErrorCause.SPEED_GAP


def test_syntax_questions_are_classified_as_parsing(tmp_path):
    with connect(tmp_path / "e.db") as connection:
        cause = classify(connection, signals(domain="reading", sub_skill="syntax_parsing"))
        assert cause is ErrorCause.PARSING_GAP


def test_recognition_failures_are_vocabulary_gaps(tmp_path):
    with connect(tmp_path / "e.db") as connection:
        assert classify(connection, signals(sub_skill="recognition")) is ErrorCause.VOCABULARY_GAP


def test_recall_failure_becomes_production_gap_once_recognition_is_solid(tmp_path):
    """見れば分かるのに書けない、を「覚えていない」と混同しない。"""
    with connect(tmp_path / "e.db") as connection:
        assert classify(connection, signals()) is ErrorCause.KNOWLEDGE_GAP

        for _ in range(20):
            update_skill_state(
                connection, signals(sub_skill="recognition", correct=True, elapsed_ms=800)
            )
        assert classify(connection, signals()) is ErrorCause.PRODUCTION_GAP


def test_an_explicit_override_wins(tmp_path):
    with connect(tmp_path / "e.db") as connection:
        cause = classify(connection, signals(correct=True, elapsed_ms=100), override="material_gap")
        assert cause is ErrorCause.MATERIAL_GAP


def _seed(connection) -> None:
    """attempt は session と item を外部キーで要求するので、先に土台を作る。"""
    connection.execute(
        "INSERT INTO material (review_id, course_id, title, source_file, section_file,"
        " source_commit, updated_at) VALUES (?, 'dsa', 'リスト', 'src/chapters/ch02.tex',"
        " 'sections/ch02-01.md', 'abc123', '2026-07-30T00:00:00+00:00')",
        (REVIEW_ID,),
    )
    connection.execute(
        "INSERT INTO learning_session (id, course_id, started_at)"
        " VALUES (1, 'dsa', '2026-07-30T00:00:00+00:00')"
    )
    connection.execute(
        "INSERT INTO generated_item (id, kind, review_id, course_id, payload, difficulty, reason,"
        " generated_by, prompt_version, source_commit, created_at)"
        " VALUES (1, 'vocab', ?, 'dsa', '{}', 2, 'test', 'claude', '2026-07-30.1', 'abc123',"
        " '2026-07-30T00:00:00+00:00')",
        (REVIEW_ID,),
    )
    connection.commit()


def _record_failure(connection, cause: str) -> None:
    update_skill_state(connection, signals())
    connection.execute(
        "INSERT INTO attempt (session_id, item_id, review_id, domain, sub_skill, correct,"
        " elapsed_ms, error_cause, created_at) VALUES (1, 1, ?, 'vocabulary', 'recall', 0,"
        " 3000, ?, '2026-07-30T00:00:00+00:00')",
        (REVIEW_ID, cause),
    )
    connection.commit()


def test_a_single_mistake_does_not_blame_the_material(tmp_path):
    with connect(tmp_path / "e.db") as connection:
        _seed(connection)
        _record_failure(connection, "knowledge_gap")
        assert escalate(connection, REVIEW_ID, "vocabulary", "recall") is False


def test_repeated_knowledge_gaps_escalate_to_a_material_gap(tmp_path):
    with connect(tmp_path / "e.db") as connection:
        _seed(connection)
        for _ in range(3):
            _record_failure(connection, "knowledge_gap")
        assert escalate(connection, REVIEW_ID, "vocabulary", "recall") is True


def test_repeated_vocabulary_gaps_do_not_escalate(tmp_path):
    """語彙不足の反復は資料の書き方の問題ではないので、資料修正へ回さない。"""
    with connect(tmp_path / "e.db") as connection:
        _seed(connection)
        for _ in range(5):
            _record_failure(connection, "vocabulary_gap")
        assert escalate(connection, REVIEW_ID, "vocabulary", "recall") is False


def test_a_correct_answer_resets_the_streak(tmp_path):
    with connect(tmp_path / "e.db") as connection:
        _seed(connection)
        for _ in range(3):
            _record_failure(connection, "knowledge_gap")
        update_skill_state(connection, signals(correct=True))
        assert escalate(connection, REVIEW_ID, "vocabulary", "recall") is False


def test_revision_candidates_are_not_duplicated(tmp_path):
    with connect(tmp_path / "e.db") as connection:
        first = open_revision_candidate(
            connection, REVIEW_ID, "dsa", "src/chapters/ch02.tex", "t", "p", ["fix"], {}
        )
        second = open_revision_candidate(
            connection, REVIEW_ID, "dsa", "src/chapters/ch02.tex", "t", "p", ["fix"], {}
        )
        assert first == second


def test_each_cause_routes_somewhere_different():
    actions = {next_action(cause) for cause in ErrorCause}
    assert len(actions) == len(ErrorCause)
    assert next_action(None) == "none"
