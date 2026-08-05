"""単語テストの出題ローテーション（次サイクルまで重複させない）とMCQ組み立て。"""

from acenglish.vocab_quiz import VocabEntry, build_choices, next_batch


def _pool(n: int) -> list[VocabEntry]:
    return [
        VocabEntry(review_id=f"toeic.words.{i:04d}", word=f"word{i}", meaning=f"意味{i}", example="")
        for i in range(n)
    ]


def test_next_batch_does_not_repeat_within_a_cycle(tmp_path):
    pool = _pool(10)

    seen_ids: set[str] = set()
    for _ in range(3):
        batch, state = next_batch(pool, count=3, home=tmp_path)
        batch_ids = {entry.review_id for entry in batch}
        # 同じサイクル内（cycle==1）では既出のIDと重ならない
        assert not (batch_ids & seen_ids)
        seen_ids |= batch_ids
        assert state["cycle"] == 1


def test_next_batch_reshuffles_into_a_new_cycle_when_pool_is_exhausted(tmp_path):
    pool = _pool(5)

    first_batch, first_state = next_batch(pool, count=5, home=tmp_path)
    assert first_state["cycle"] == 1
    assert {e.review_id for e in first_batch} == {e.review_id for e in pool}

    # プールを使い切った直後の呼び出しは、次サイクルへ入って再シャッフルされる
    second_batch, second_state = next_batch(pool, count=5, home=tmp_path)
    assert second_state["cycle"] == 2
    assert {e.review_id for e in second_batch} == {e.review_id for e in pool}


def test_next_batch_persists_state_across_calls(tmp_path):
    pool = _pool(20)

    next_batch(pool, count=8, home=tmp_path)
    _, state = next_batch(pool, count=8, home=tmp_path)

    assert state["cursor"] == 16


def test_build_choices_includes_the_correct_meaning_exactly_once():
    pool = _pool(20)
    target = pool[0]

    choices, answer_index = build_choices(target, pool, n_choices=4)

    assert len(choices) == 4
    assert choices.count(target.meaning) == 1
    assert choices[answer_index] == target.meaning


def test_build_choices_never_uses_the_target_word_as_its_own_distractor():
    pool = _pool(6)
    target = pool[0]

    choices, _ = build_choices(target, pool, n_choices=4)

    # 誤答側に自分自身の意味が重複して2回出てこないことだけ確認する
    # （正解1つ分は含まれるので、意味の一致は1回のみ）
    assert choices.count(target.meaning) == 1
