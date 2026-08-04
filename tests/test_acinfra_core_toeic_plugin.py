from acenglish.db import connect as connect_acenglish
from acinfra_core.plugins.toeic import TOEIC_COMPETENCIES, ToeicPlugin


def _insert_skill_state(connection, target_ref, mastery, confidence, attempts, error_streak=0):
    connection.execute(
        "INSERT INTO skill_state (domain, sub_skill, target_ref, mastery, confidence,"
        " hint_rate, error_streak, attempts, updated_at) VALUES"
        " ('vocabulary', 'recall', ?, ?, ?, 0.0, ?, ?, '2026-08-04T00:00:00+00:00')",
        (target_ref, mastery, confidence, error_streak, attempts),
    )
    connection.commit()


def test_competencies_returns_the_static_taxonomy(tmp_path):
    with connect_acenglish(tmp_path / "english.db") as connection:
        plugin = ToeicPlugin(connection)
        ids = {c.competency_id for c in plugin.competencies()}
    assert ids == {c.competency_id for c in TOEIC_COMPETENCIES}


def test_mastery_summary_is_weighted_by_attempts(tmp_path):
    with connect_acenglish(tmp_path / "english.db") as connection:
        _insert_skill_state(connection, "toeic.core500.0001", mastery=0.8, confidence=0.9, attempts=8)
        _insert_skill_state(connection, "toeic.core500.0002", mastery=0.2, confidence=0.5, attempts=2)
        # このデッキ以外の語彙は含めない
        _insert_skill_state(connection, "dsa.ch01.list.s01.vocab.0001", mastery=1.0, confidence=1.0, attempts=100)

        plugin = ToeicPlugin(connection)
        vocab = next(c for c in plugin.competencies() if c.competency_id == "toeic.vocabulary.recall")
        summary = plugin.mastery_summary([vocab])["toeic.vocabulary.recall"]

    assert summary.attempts == 10
    assert summary.mastery == 0.68  # (0.8*8 + 0.2*2) / 10


def test_mastery_summary_reports_no_attempts_honestly(tmp_path):
    with connect_acenglish(tmp_path / "english.db") as connection:
        plugin = ToeicPlugin(connection)
        vocab = next(c for c in plugin.competencies() if c.competency_id == "toeic.vocabulary.recall")
        summary = plugin.mastery_summary([vocab])["toeic.vocabulary.recall"]

    assert summary.mastery is None
    assert summary.attempts == 0
    assert summary.note == "attemptが無い"


def test_mastery_summary_reports_unconnected_competencies(tmp_path):
    with connect_acenglish(tmp_path / "english.db") as connection:
        plugin = ToeicPlugin(connection)
        part5 = next(c for c in plugin.competencies() if c.competency_id == "toeic.part5.grammar")
        summary = plugin.mastery_summary([part5])["toeic.part5.grammar"]

    assert summary.mastery is None
    assert "未接続" in summary.note


def test_resource_gap_hint_flags_low_mastery(tmp_path):
    with connect_acenglish(tmp_path / "english.db") as connection:
        _insert_skill_state(connection, "toeic.core500.0001", mastery=0.1, confidence=0.3, attempts=10)
        plugin = ToeicPlugin(connection)
        vocab = next(c for c in plugin.competencies() if c.competency_id == "toeic.vocabulary.recall")
        summary = plugin.mastery_summary([vocab])["toeic.vocabulary.recall"]
        hint = plugin.resource_gap_hint(vocab, summary)

    assert hint is not None
    assert hint.gap_kind == "difficulty"


def test_resource_gap_hint_is_none_for_healthy_mastery(tmp_path):
    with connect_acenglish(tmp_path / "english.db") as connection:
        _insert_skill_state(connection, "toeic.core500.0001", mastery=0.9, confidence=0.9, attempts=10)
        plugin = ToeicPlugin(connection)
        vocab = next(c for c in plugin.competencies() if c.competency_id == "toeic.vocabulary.recall")
        summary = plugin.mastery_summary([vocab])["toeic.vocabulary.recall"]
        hint = plugin.resource_gap_hint(vocab, summary)

    assert hint is None
