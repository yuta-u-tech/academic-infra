"""evidenceから次の生成対象を決めるハブ。特に toeic-source 除外(実データで踏んだ制約)を固定する。"""

import pytest

from acenglish import generate, regenerate, study
from acenglish.db import connect
from acenglish.items import GenerationResult
from acenglish.sources.base import ExternalMaterial
from acenglish.target import LearningTarget

TARGET = LearningTarget(
    review_id="english.regenerate.s01",
    course_id="english",
    title="regenerate fixture",
    chapter_title="regenerate fixture",
    source_file="src/regenerate.tex",
    section_file="sections/regenerate.md",
    source_commit="abc123",
    body="regenerate fixture body",
)

TOEIC_TARGET = ExternalMaterial(
    review_id="toeic.words1-400.0001",
    source="toeic",
    title="TOEIC vocab",
    body="preside",
    origin="words1-400",
    source_file="toeic/words1-400.md",
    source_commit="words1-400",
)


def _target_result() -> GenerationResult:
    return GenerationResult.model_validate(
        {
            "review_id": TARGET.review_id,
            "course_id": TARGET.course_id,
            "source_commit": "abc123",
            "generated_by": "claude-opus-5",
            "prompt_version": "2026-07-30.1",
            "items": [
                {
                    "difficulty": 3,
                    "reason": "語彙",
                    "item": {
                        "kind": "vocab",
                        "sub_skill": "recall",
                        "word": "presided",
                        "meaning": "主宰した",
                        "example": "She presided over the meeting.",
                    },
                }
            ],
        }
    )


def _toeic_result() -> GenerationResult:
    return GenerationResult.model_validate(
        {
            "review_id": TOEIC_TARGET.review_id,
            "course_id": TOEIC_TARGET.course_id,
            "source_commit": TOEIC_TARGET.source_commit,
            "generated_by": "claude-opus-5",
            "prompt_version": "2026-07-30.1",
            "items": [
                {
                    "difficulty": 3,
                    "reason": "TOEIC語彙",
                    "item": {
                        "kind": "vocab",
                        "sub_skill": "recall",
                        "word": "preside",
                        "meaning": "主宰する",
                    },
                }
            ],
        }
    )


@pytest.fixture
def db(tmp_path):
    connection = connect(tmp_path / "english.db")
    yield connection
    connection.close()


def test_no_evidence_raises(db):
    generate.upsert_material(db, TARGET)
    generate.ingest(db, _target_result())

    with pytest.raises(regenerate.NoEvidenceError):
        regenerate.pick_next_target(db, "english")


def test_toeic_source_is_excluded_even_when_it_is_the_weakest(db):
    """実データで踏んだケース: mastery最下位がtoeic-sourceのとき、次点にフォールバックする。"""
    generate.upsert_material(db, TARGET)
    generate.upsert_material(db, TOEIC_TARGET)
    (target_vocab_id,) = generate.ingest(db, _target_result())
    (toeic_vocab_id,) = generate.ingest(db, _toeic_result())

    session_id = study.start_session(db, "english")
    # TOEIC語彙は不正解を繰り返し、vocabulary domain内で最もmasteryを低くする。
    for _ in range(3):
        study.answer(db, session_id, toeic_vocab_id, "wrong", elapsed_ms=2_000)
    # TARGET語彙は正解させ、toeicより高いmasteryにしておく。
    study.answer(db, session_id, target_vocab_id, "presided", elapsed_ms=1_000, self_confidence=1.0)

    review_id, kind = regenerate.pick_next_target(db, "english")

    assert kind == "vocab"
    assert review_id == TARGET.review_id, "toeic-sourceは除外され、次点(academic)が選ばれるべき"


def test_no_regenerable_target_when_only_toeic_material_exists(db):
    generate.upsert_material(db, TOEIC_TARGET)
    (toeic_vocab_id,) = generate.ingest(db, _toeic_result())
    session_id = study.start_session(db, "english")
    study.answer(db, session_id, toeic_vocab_id, "wrong", elapsed_ms=2_000)

    with pytest.raises(regenerate.NoRegenerableTargetError):
        regenerate.pick_next_target(db, "english")


def test_the_weakest_domain_is_selected_and_mapped_to_its_kind(db):
    generate.upsert_material(db, TARGET)
    (vocab_id,) = generate.ingest(db, _target_result())
    session_id = study.start_session(db, "english")

    # 唯一のdomain(vocabulary)なので、それが選ばれkindはvocabに変換される。
    study.answer(db, session_id, vocab_id, "presided", elapsed_ms=1_000, self_confidence=1.0)

    review_id, kind = regenerate.pick_next_target(db, "english")
    assert (review_id, kind) == (TARGET.review_id, "vocab")
