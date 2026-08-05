"""evidence(skill_state)から「次に何を生成すべきか」を決めるハブ。

`generate.request()` は対象(review_id)・種別(kinds)・件数を呼び出し側が手で指定する
前提で、evidence(学習時間・正答率・誤答分類の集計結果である mastery)を見ない。
ここはその前段として (review_id, kind) だけを決める。生成依頼JSONの組み立てや
実際の生成・取り込みには一切手を出さない（`generate.request()`/`ingest()`をそのまま使う）。

domain単位の「手薄」判定は dashboard.py と完全に同じロジックにする
（同じSQLを2箇所に書くと、ダッシュボードの表示と生成対象の判断がずれる）。
"""

from __future__ import annotations

import sqlite3

from .dashboard import _mastery_by_domain, _weakest_domain

_DOMAIN_TO_KIND = {"vocabulary": "vocab", "reading": "reading", "grammar": "grammar"}


class NoEvidenceError(Exception):
    """このcourseにまだ学習実績(skill_state)が無い。"""


class NoRegenerableTargetError(Exception):
    """対象になり得る material が1件も無い(source='toeic'しか無い等)。"""


def _weakest_regenerable_target(
    connection: sqlite3.Connection, course_id: str, domain: str
) -> str | None:
    """domain内でmasteryが最も低いreview_idを探す。

    material.source = 'toeic' は除外する。`fetch.load_material()` がTOEIC語彙の
    本文を取り直せず None を返す(既にカード化済みで取得元が無いため)ので、
    `generate.request()` に渡しても解決できない。
    """
    row = connection.execute(
        """
        SELECT ss.target_ref AS review_id
        FROM skill_state ss
        JOIN material m ON m.review_id = ss.target_ref
        WHERE m.course_id = ? AND ss.domain = ? AND ss.attempts > 0 AND m.source != 'toeic'
        ORDER BY ss.mastery ASC, ss.attempts DESC
        LIMIT 1
        """,
        (course_id, domain),
    ).fetchone()
    return row["review_id"] if row else None


def _fallback_target(connection: sqlite3.Connection, course_id: str, kind: str) -> str | None:
    """該当domainでskill_stateが無い場合、直近更新のmaterialへフォールバックする。

    こちらも source='toeic' は除外する(理由は _weakest_regenerable_target と同じ)。
    """
    row = connection.execute(
        """
        SELECT DISTINCT gi.review_id AS review_id, m.updated_at AS updated_at
        FROM generated_item gi
        JOIN material m ON m.review_id = gi.review_id
        WHERE gi.course_id = ? AND gi.kind = ? AND gi.retired_at IS NULL AND m.source != 'toeic'
        ORDER BY m.updated_at DESC
        LIMIT 1
        """,
        (course_id, kind),
    ).fetchone()
    return row["review_id"] if row else None


def pick_next_target(connection: sqlite3.Connection, course_id: str) -> tuple[str, str]:
    """evidenceから次に生成すべき (review_id, kind) を決める。"""
    mastery_by_domain = _mastery_by_domain(connection, course_id)
    domain = _weakest_domain(mastery_by_domain)
    if domain is None:
        # skill_state は最初の回答時にしか作られない(常にattempts>=1)ので、
        # domainがNoneになるのはmastery_by_domainが空(=学習実績が皆無)のときだけ。
        raise NoEvidenceError(
            f"course_id={course_id!r} にはまだ学習実績がありません。"
            "先に何度か学習してから next-request を使ってください。"
        )
    kind = _DOMAIN_TO_KIND[domain]

    review_id = _weakest_regenerable_target(connection, course_id, domain)
    if review_id is None:
        review_id = _fallback_target(connection, course_id, kind)
    if review_id is None:
        raise NoRegenerableTargetError(
            f"course_id={course_id!r} domain={domain!r} には生成依頼を作れる対象"
            "(source が toeic 以外の material)がありません。"
        )
    return review_id, kind
