"""外部素材（TOEIC語彙・VOA記事・TED字幕）の取り込み。通信はしない。"""

import pytest

from acenglish.sources import note_path_for, slugify
from acenglish.sources.base import ExternalMaterial
from acenglish.sources.studyforge import DeckNotFoundError, fetch_deck, iter_materials, split_example
from acenglish.sources.ted import parse_vtt
from acenglish.sources.voa import ArticleFetchError, parse_article, to_material


def test_review_ids_must_name_their_source():
    """後から「これはどこから来た素材か」を ID だけで言えるようにしておく。"""
    with pytest.raises(ValueError, match="で始める必要があります"):
        ExternalMaterial(
            review_id="wrong.prefix",
            source="voa",
            title="t",
            body="b",
            origin="https://example.com",
            source_file="notes/reading/voa.md",
            source_commit="x",
        )


def test_slugs_stay_stable_and_ascii():
    assert slugify("The Goodyear Blimp Has Been Flying") == "the-goodyear-blimp-has-been-flying"
    assert slugify("日本語だけ") == "untitled"
    assert slugify("a" * 200) == "a" * 60


def test_notes_are_split_by_domain():
    assert note_path_for("vocabulary", "toeic-words1-400") == "notes/vocabulary/toeic-words1-400.md"
    assert note_path_for("grammar", "part5") == "notes/grammar/part5.md"
    assert note_path_for("listening", "ted") == "notes/reading/ted.md"


# --- study-forge (TOEIC) -------------------------------------------------

def test_an_unknown_deck_is_refused_before_any_request():
    with pytest.raises(DeckNotFoundError, match="words1-400"):
        fetch_deck("does-not-exist")


def test_the_english_sentence_is_lifted_out_of_the_example_field():
    """study-forge の example は「解説。例: <英文>（<訳>）」という1本の文字列。"""
    english, japanese = split_example(
        "直後や次の情報を示す。例: Following the speech, we had dinner.（スピーチに続いて夕食をとった）"
    )
    assert english == "Following the speech, we had dinner."
    assert japanese == "スピーチに続いて夕食をとった"


def test_an_example_without_the_marker_yields_no_english():
    """壊れた英文を教材に混ぜるより、例文なしの方がまし。"""
    english, japanese = split_example("説明だけで例文がない")
    assert english is None
    assert japanese == "説明だけで例文がない"


def test_an_empty_example_is_handled():
    assert split_example("") == (None, None)


def test_each_word_becomes_its_own_learning_target():
    """デッキ単位にすると981語が1つの習熟度に丸められる。"""
    terms = [
        {"term": "anyway", "definition": "とにかく", "example": "例: Anyway, let's try.（やってみよう）"},
        {"term": "following", "definition": "次の", "example": ""},
    ]
    pairs = list(iter_materials("words1-400", terms))

    assert [m.review_id for m, _ in pairs] == [
        "toeic.words1-400.0001",
        "toeic.words1-400.0002",
    ]
    assert pairs[0][1].word == "anyway"
    assert pairs[0][1].example == "Anyway, let's try."
    assert pairs[1][1].example is None


def test_toeic_errors_are_routed_to_the_vocabulary_note():
    material, _ = next(iter_materials("words1-400", [{"term": "a", "definition": "b"}]))
    assert material.source_file == "notes/vocabulary/toeic-words1-400.md"
    assert material.source == "toeic"


def test_entries_missing_a_term_or_definition_are_skipped():
    terms = [{"term": "", "definition": "x"}, {"term": "y", "definition": ""}, {"term": "ok", "definition": "可"}]
    assert [item.word for _, item in iter_materials("d", terms)] == ["ok"]


# --- VOA -----------------------------------------------------------------

VOA_HTML = """
<html><body>
<div class="wsw"><div class="media-pholder"><p>Short</p></div>
<p>Wilbur and Orville Wright are the American inventors who made a small engine-powered flying machine.</p>
<p>As they grew up, the Wright brothers experimented with mechanical things in their shop.</p>
<p>Marilyn Rice Christiano wrote this story for VOA Learning English.</p>
<p>______________________________________________________</p>
<p>glider - n. a flying object similar to an airplane but without an engine</p>
</div></body></html>
"""


def test_the_article_body_survives_the_player_markup():
    """VOA は本文の前に音声プレイヤーの入れ子 div を大量に挟む。"""
    article = parse_article(VOA_HTML, "Wright", "https://example.com/a/wright/1.html")
    assert len(article.paragraphs) == 2
    assert article.paragraphs[0].startswith("Wilbur and Orville Wright")


def test_credits_and_rules_are_not_treated_as_content():
    article = parse_article(VOA_HTML, "Wright", "https://example.com/a/wright/1.html")
    assert not any("wrote this story" in p for p in article.paragraphs)
    assert not any(set(p) == {"_"} for p in article.paragraphs)


def test_the_articles_own_glossary_is_kept():
    """VOA は記事末尾に語注を付ける。教材の素材としてそのまま使える。"""
    article = parse_article(VOA_HTML, "Wright", "https://example.com/a/wright/1.html")
    assert "glider" in article.glossary
    assert article.glossary["glider"].startswith("n.")


def test_an_article_with_no_body_is_an_error():
    with pytest.raises(ArticleFetchError, match="本文を抽出できませんでした"):
        parse_article("<html><p>too short</p></html>", "t", "https://example.com/x.html")


def test_the_glossary_travels_with_the_material():
    article = parse_article(VOA_HTML, "Wright", "https://example.com/a/wright-brothers/7998765.html")
    material = to_material(article)
    assert material.review_id == "voa.7998765"
    assert "記事に付属する語注" in material.body
    assert material.source_file == "notes/reading/voa.md"


# --- TED -----------------------------------------------------------------

VTT = """WEBVTT
Kind: captions
Language: en

00:00:01.000 --> 00:00:04.000
So I want to tell you a story.

00:00:04.000 --> 00:00:06.000
So I want to tell you a story.

00:00:06.000 --> 00:00:09.000
It begins in a small town. The town had one road.
"""


def test_subtitles_become_sentences():
    assert parse_vtt(VTT) == [
        "So I want to tell you a story.",
        "It begins in a small town.",
        "The town had one road.",
    ]


def test_the_karaoke_duplication_of_auto_captions_is_dropped():
    """自動字幕は同じ行を送り出しながら重複して出す。"""
    assert parse_vtt(VTT).count("So I want to tell you a story.") == 1


def test_timestamps_and_headers_never_reach_the_material():
    body = " ".join(parse_vtt(VTT))
    assert "WEBVTT" not in body
    assert "-->" not in body
