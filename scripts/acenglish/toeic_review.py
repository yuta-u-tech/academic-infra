"""間違えたTOEIC問題を1枚の復習ノートに集約する。

出題はドメインごとに別スクリプト（part5/part7/listening/vocab）で動くが、試験前に
見返す資料はドメインを跨いで1つにまとめたい。ここでは「今も間違えたまま」（同じ
review_id の最新試行が不正解）のものだけを拾う。一度マスターした（後で正解した）
問題は自動的に外れる — 復習が要らなくなったものを載せ続けても資料が肥大化するだけ
なので。

生成はフルリビルド。手作業で書く部分（動画プレイリンク等の目次）と機械生成部分は
AUTO-GENERATED マーカーで分け、リビルドのたびに後者だけ差し替える。
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from .notes import NotesRepositoryError, notes_home

MISC_DIR = "TOEIC_MISC"
REVIEW_FILENAME = "toeic-review.md"

_BEGIN_MARKER = "<!-- AUTO-GENERATED:BEGIN -->"
_END_MARKER = "<!-- AUTO-GENERATED:END -->"
_MARKER_PATTERN = re.compile(re.escape(_BEGIN_MARKER) + r".*?" + re.escape(_END_MARKER), re.DOTALL)

_SECTION_ORDER = ("grammar", "reading_part6", "reading_part7", "listening", "vocabulary")
_SECTION_TITLES = {
    "grammar": "Part5（文法）",
    "reading_part6": "Part6（長文穴埋め）",
    "reading_part7": "Part7（読解）",
    "listening": "リスニング",
    "vocabulary": "語彙",
}


def _section_key(row: dict) -> str:
    """domain='reading'にはPart6(reading_blank)とPart7(reading)が両方乗るので、
    kindで節を分ける（節見出しが「Part7」固定のままPart6が混ざるのを防ぐ）。
    """
    domain = row["domain"]
    if domain != "reading":
        return domain
    payload = json.loads(row["payload"])
    return "reading_part6" if payload.get("kind") == "reading_blank" else "reading_part7"

_DEFAULT_HEADER = """# TOEIC 復習ノート

このファイル1つで、試験前の見直しが済むようにする。

## 目次

- 復習動画プレイリスト: <ここにYouTube再生リストのURLを貼る>

## 間違えている問題（現在時点）

間違えたが後で正解した問題は次回更新時に自動的に消える。まだ間違えたままのものだけが並ぶ。
"""


def review_path(home: Path | None = None) -> Path:
    return (home or notes_home()) / MISC_DIR / REVIEW_FILENAME


def fetch_wrong_items(connection: sqlite3.Connection, *, since_date: str | None = None) -> list[dict]:
    """今も間違えたままのTOEIC問題を返す（review_id単位、最新試行が不正解のものだけ）。

    `since_date`（"YYYY-MM-DD"）を渡すと、その日以降に解答した試行だけに絞る。
    復習ノート/PDF（試験前に見返す資料。一度マスターしたら自動的に外れる設計）は
    全期間が正しいので既定のNoneのまま呼ぶ。**復習動画は「その日に間違えた問題」を
    対象にする設計**（2026-08-14、間違えて全期間分（55問）を1本の動画にしてしまい、
    レンダラーが長時間ジョブでハングする不具合を誘発した反省から明確化。動画生成の
    呼び出し側は必ず`since_date=today`を渡すこと）。
    """
    rows = connection.execute(
        """
        SELECT a.review_id, a.domain, a.created_at, a.error_cause, a.correct, g.payload
        FROM attempt a
        JOIN generated_item g ON a.item_id = g.id
        WHERE a.review_id LIKE 'toeic.%'
        ORDER BY a.review_id, a.created_at ASC, a.id ASC
        """
    ).fetchall()

    latest: dict[str, dict] = {}
    for row in rows:
        latest[row["review_id"]] = dict(row)  # 同じreview_idは後勝ち = 最新試行

    wrong = [row for row in latest.values() if not row["correct"]]
    if since_date is not None:
        wrong = [row for row in wrong if row["created_at"][:10] >= since_date]
    wrong.sort(key=lambda row: row["created_at"], reverse=True)
    return wrong


def _choice_line(payload: dict) -> str:
    choices = payload["choices"]
    answer = choices[payload["answer_index"]]
    return f"  - 選択肢: {' / '.join(choices)}\n  - 正解: {answer}"


def _format_item(row: dict) -> str:
    payload = json.loads(row["payload"])
    kind = payload.get("kind")
    header = f"- `{row['review_id']}`（誤答日: {row['created_at'][:10]}、原因: {row['error_cause'] or '-'}）"
    lines = [header]

    if kind == "grammar":
        lines.append(f"  - 問題: {payload['sentence']}")
        lines.append(_choice_line(payload))
        lines.append(f"  - 論点: {payload.get('point', '-')}")
        lines.append(f"  - 解説: {payload['explanation']}")
    elif kind == "reading":
        passage = payload["passage"]
        if len(passage) > 500:
            passage = passage[:500] + "…"
        lines.append(f"  - パッセージ: {passage}")
        lines.append(f"  - 設問: {payload['question']}")
        lines.append(_choice_line(payload))
        lines.append(f"  - 解説: {payload['explanation']}")
    elif kind == "reading_blank":
        passage = payload["passage"]
        if len(passage) > 500:
            passage = passage[:500] + "…"
        lines.append(f"  - パッセージ: {passage}")
        lines.append(f"  - 空所: [{payload['blank_number']}]（{payload.get('blank_type', 'word')}）")
        lines.append(_choice_line(payload))
        lines.append(f"  - 論点: {payload.get('point', '-')}")
        lines.append(f"  - 解説: {payload['explanation']}")
    elif kind == "listening":
        lines.append(f"  - 設問: {payload['question']}")
        lines.append(_choice_line(payload))
        lines.append(f"  - 解説: {payload['explanation']}")
    elif kind == "vocab":
        lines.append(f"  - 語: {payload['word']}")
        lines.append(f"  - 意味: {payload['meaning']}")
        if payload.get("example"):
            lines.append(f"  - 例文: {payload['example']}")

    return "\n".join(lines)


def render_body(items: list[dict]) -> str:
    if not items:
        return "現在、間違えたまま残っている問題はありません。"

    by_section: dict[str, list[dict]] = {}
    for item in items:
        by_section.setdefault(_section_key(item), []).append(item)

    sections = []
    for section in _SECTION_ORDER:
        rows = by_section.get(section)
        if not rows:
            continue
        sections.append(f"### {_SECTION_TITLES[section]}（{len(rows)}問）\n\n" + "\n\n".join(_format_item(r) for r in rows))
    return "\n\n".join(sections)


def render_review_markdown(existing: str | None, items: list[dict]) -> str:
    """既存ファイルの AUTO-GENERATED 区間だけを差し替える。手作業で書いた目次は触らない。"""
    block = f"{_BEGIN_MARKER}\n\n{render_body(items)}\n\n{_END_MARKER}"
    if existing and _MARKER_PATTERN.search(existing):
        return _MARKER_PATTERN.sub(block, existing)
    header = existing.rstrip("\n") + "\n\n" if existing else _DEFAULT_HEADER
    return f"{header}\n{block}\n"


def write_review(connection: sqlite3.Connection, home: Path | None = None) -> Path:
    root = home or notes_home()
    if not (root / ".git").exists():
        raise NotesRepositoryError(
            f"{root} が english-notes リポジトリではありません。"
            f"別の場所を使うなら ENGLISH_NOTES_HOME を設定してください。"
        )
    path = root / MISC_DIR / REVIEW_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else None
    items = fetch_wrong_items(connection)
    path.write_text(render_review_markdown(existing, items), encoding="utf-8")
    return path


PDF_TITLE = "TOEIC 復習ノート"
PDF_FILENAME = "toeic-review.pdf"

_PDF_PREAMBLE = r"""\documentclass[a4paper,11pt]{ltjsarticle}
\usepackage{luatexja}
\usepackage[margin=25mm]{geometry}
\usepackage{enumitem}
\usepackage{hyperref}
\hypersetup{hidelinks}
\setlist[enumerate]{itemsep=6pt,topsep=4pt}
\renewcommand{\thesection}{}
"""


def _playlist_line(playlist_url: str | None) -> list[str]:
    if not playlist_url:
        return []
    # 冊子(worksheet.py)のForm/YouTube埋め込みと同じ考え方。別ファイルに書くだけでは
    # 「今読んでいる解説」から動画へ辿れないので、PDF本文の先頭に必ず埋め込む。
    return [r"\par\noindent\textbf{復習動画プレイリスト:} \href{" + playlist_url + r"}{YouTubeで見る}", ""]


def _tex_choice_lines(payload: dict, escape) -> list[str]:
    choices = payload["choices"]
    answer = choices[payload["answer_index"]]
    return [
        r"    \par\noindent 選択肢: " + escape(" / ".join(choices)),
        r"    \par\noindent \textbf{正解: " + escape(answer) + "}",
    ]


def _tex_item(row: dict, escape) -> list[str]:
    """Markdown版の `_format_item` と同じ内容を、同じ4種のkind分岐でTeXにする。"""
    payload = json.loads(row["payload"])
    kind = payload.get("kind")
    lines = [r"\item \textbf{" + escape(row["review_id"]) + "}"]

    if kind == "grammar":
        lines.append(r"    \par\noindent " + escape(payload["sentence"]))
        lines.extend(_tex_choice_lines(payload, escape))
        lines.append(r"    \par\noindent 論点: " + escape(payload.get("point", "-")))
        lines.append(r"    \par\smallskip\noindent " + escape(payload["explanation"]))
    elif kind == "reading":
        passage = payload["passage"]
        if len(passage) > 500:
            passage = passage[:500] + "…"
        lines.append(r"    \par\noindent パッセージ: " + escape(passage))
        lines.append(r"    \par\noindent 設問: " + escape(payload["question"]))
        lines.extend(_tex_choice_lines(payload, escape))
        lines.append(r"    \par\smallskip\noindent " + escape(payload["explanation"]))
    elif kind == "reading_blank":
        passage = payload["passage"]
        if len(passage) > 500:
            passage = passage[:500] + "…"
        lines.append(r"    \par\noindent パッセージ: " + escape(passage))
        lines.append(
            r"    \par\noindent 空所: " + escape(f"[{payload['blank_number']}]（{payload.get('blank_type', 'word')}）")
        )
        lines.extend(_tex_choice_lines(payload, escape))
        lines.append(r"    \par\noindent 論点: " + escape(payload.get("point", "-")))
        lines.append(r"    \par\smallskip\noindent " + escape(payload["explanation"]))
    elif kind == "listening":
        lines.append(r"    \par\noindent 設問: " + escape(payload["question"]))
        lines.extend(_tex_choice_lines(payload, escape))
        lines.append(r"    \par\smallskip\noindent " + escape(payload["explanation"]))
    elif kind == "vocab":
        lines.append(r"    \par\noindent 語: " + escape(payload["word"]))
        lines.append(r"    \par\noindent 意味: " + escape(payload["meaning"]))
        if payload.get("example"):
            lines.append(r"    \par\smallskip\noindent 例文: " + escape(payload["example"]))

    return lines


def render_tex(items: list[dict], playlist_url: str | None = None) -> str:
    from academic_audio.worksheet import escape

    lines = [
        _PDF_PREAMBLE, r"\title{" + escape(PDF_TITLE) + "}", r"\date{}", r"\begin{document}", r"\maketitle",
        *_playlist_line(playlist_url),
    ]

    if not items:
        lines.append(escape("現在、間違えたまま残っている問題はありません。"))
        lines.append(r"\end{document}")
        return "\n".join(lines) + "\n"

    by_section: dict[str, list[dict]] = {}
    for item in items:
        by_section.setdefault(_section_key(item), []).append(item)

    for section in _SECTION_ORDER:
        rows = by_section.get(section)
        if not rows:
            continue
        lines.append(r"\section*{" + escape(f"{_SECTION_TITLES[section]}（{len(rows)}問）") + "}")
        lines.append(r"\begin{enumerate}[label=\textbf{\arabic*.}]")
        for row in rows:
            lines.extend(_tex_item(row, escape))
        lines.append(r"\end{enumerate}")

    lines.append(r"\end{document}")
    return "\n".join(lines) + "\n"


def write_pdf(connection: sqlite3.Connection, out_dir: Path, playlist_url: str | None = None) -> Path:
    """PDFは常に同じファイル名(`toeic-review.pdf`)で書く。呼び出し側がDriveへ同名で
    publishすれば、既存ファイルが更新される（日付付き名にすると毎回別ファイルになる）。
    `playlist_url` を渡すと、PDF本文の先頭にその場でリンクを埋め込む（別ファイルの
    目次に書くだけでは、読んでいる解説から動画へ辿れないため）。
    """
    from academic_audio.worksheet import build_pdf

    out_dir.mkdir(parents=True, exist_ok=True)
    items = fetch_wrong_items(connection)
    tex_path = out_dir / PDF_FILENAME.replace(".pdf", ".tex")
    tex_path.write_text(render_tex(items, playlist_url), encoding="utf-8")
    return build_pdf(tex_path)
