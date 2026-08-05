"""外部素材の取り込みを1つの入口にまとめる。

取得元ごとの差（HTTP か yt-dlp か、語彙が既にあるか本文だけか）は `sources/` が吸収し、
ここから先は科目資料と同じ `material` + `generated_item` になる。
"""

from __future__ import annotations

import sqlite3

from .generate import ingest, upsert_material
from .items import GrammarItem
from .sources import ExternalMaterial
from .sources import studyforge, ted, toeic_part5, toeic_part7, voa
from .sources.toeic_part7 import Part7Passage


def import_toeic_deck(connection: sqlite3.Connection, deck: str, limit: int | None = None) -> int:
    """TOEIC 語彙デッキを取り込む。既に語義・例文があるので生成を挟まない。

    再取り込みしても語彙カードが二重にならないよう、その語について既にカードがあれば飛ばす。
    デッキは何度も引き直すもの（単語集の改訂・取りこぼしの拾い直し）なので、冪等でないと困る。
    """
    payload = studyforge.fetch_deck(deck)
    terms = payload.get("terms", [])
    if limit is not None:
        terms = terms[:limit]

    imported = 0
    for material, item in studyforge.iter_materials(deck, terms):
        upsert_material(connection, material)
        existing = connection.execute(
            "SELECT 1 FROM generated_item WHERE review_id = ? AND kind = 'vocab'"
            " AND retired_at IS NULL LIMIT 1",
            (material.review_id,),
        ).fetchone()
        if existing:
            continue
        ingest(
            connection,
            studyforge.build_result(material, item, f"TOEIC 単語集 {deck} からの取り込み"),
        )
        imported += 1
    return imported


def import_toeic_part5(connection: sqlite3.Connection, set_id: str, items: list[GrammarItem]) -> int:
    """TOEIC Part5（空所補充）のセットを学習ループへ取り込む。

    `toeic_reading_cli.py worksheet` が組む冊子と同じ items を渡す想定。再取り込みしても
    問題が二重にならないよう、既にカードがあれば飛ばす（`import_toeic_deck` と同じ理由）。
    """
    imported = 0
    for material, item in toeic_part5.iter_materials(set_id, items):
        upsert_material(connection, material)
        existing = connection.execute(
            "SELECT 1 FROM generated_item WHERE review_id = ? AND kind = 'grammar'"
            " AND retired_at IS NULL LIMIT 1",
            (material.review_id,),
        ).fetchone()
        if existing:
            continue
        ingest(
            connection,
            toeic_part5.build_result(material, item, f"TOEIC Part5 セット {set_id} からの取り込み"),
        )
        imported += 1
    return imported


def import_toeic_part7(connection: sqlite3.Connection, set_id: str, passages: list[Part7Passage]) -> int:
    """TOEIC Part7（読解）のセットを学習ループへ取り込む。

    `import_toeic_part5` と同じ理由・同じ冪等性の作り方（`kind='reading'`で存在チェック）。
    passage内の設問はそれぞれ別のreview_idを持つ（`toeic_part7.iter_materials`参照）ので、
    1passageの一部の設問だけ既存で残りが新規、という状態も自然に扱える。
    """
    imported = 0
    for material, item in toeic_part7.iter_materials(set_id, passages):
        upsert_material(connection, material)
        existing = connection.execute(
            "SELECT 1 FROM generated_item WHERE review_id = ? AND kind = 'reading'"
            " AND retired_at IS NULL LIMIT 1",
            (material.review_id,),
        ).fetchone()
        if existing:
            continue
        ingest(
            connection,
            toeic_part7.build_result(material, item, f"TOEIC Part7 セット {set_id} からの取り込み"),
        )
        imported += 1
    return imported


def list_voa_articles(feed_url: str | None = None, limit: int = 10) -> list[dict]:
    """VOA の記事一覧。フィード未指定なら一覧ページの先頭のフィードを使う。"""
    url = feed_url or voa.list_feeds()[0]
    return voa.fetch_feed(url, limit=limit)


def import_voa_article(
    connection: sqlite3.Connection, url: str, title: str = ""
) -> ExternalMaterial:
    """VOA の記事を学習対象として登録する（問題の生成はこの後に Claude が行う）。"""
    material = voa.to_material(voa.fetch_article(url, title))
    upsert_material(connection, material)
    return material


def import_ted_talk(
    connection: sqlite3.Connection, url: str, max_sentences: int = 60
) -> ExternalMaterial:
    """TED/YouTube の字幕を学習対象として登録する。音声は落とさない。"""
    material = ted.to_material(ted.fetch_talk(url), max_sentences=max_sentences)
    upsert_material(connection, material)
    return material


def load_material(connection: sqlite3.Connection, review_id: str) -> ExternalMaterial | None:
    """取り込み済みの外部素材を、生成依頼を作れる形で読み直す。

    本文（`body`）は DB に持たせていない（正本は取得元）ので、生成依頼を作る時点で
    取得元から取り直す。TOEIC は語彙が既にカードになっているため対象外。
    """
    row = connection.execute(
        "SELECT * FROM material WHERE review_id = ?", (review_id,)
    ).fetchone()
    if row is None or row["source"] == "academic":
        return None

    if row["source"] == "voa":
        return voa.to_material(voa.fetch_article(row["origin"], row["title"]))
    if row["source"] == "ted":
        return ted.to_material(ted.fetch_talk(row["origin"]))
    return None
