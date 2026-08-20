"""単語帳PDFに「タップで開閉する黒い付箋」を実装する。

PDF Optional Content(OCG)のSetOCGStateアクション(\\switchocg等)はAdobe Acrobat専用で、
macOSのPreview.app・Chrome内蔵ビューアのどちらでも効かないことを実機確認済み
（2026-08-19）。一方、AcroFormのチェックボックス自体は両方で正常にクリック・保存できる
ことも確認済み。そこで、チェックボックス1個の「見た目」自体を差し替える
（未チェック=黒塗り、チェック=意味のテキスト）ことで、チェックボックスの標準クリック
動作をそのまま「タップで開閉」として使う。

チェックボックスの appearance stream (`/AP`) はhyperrefの`\\CheckBox`では
チェックマーク以外の任意コンテンツを指定できないため、いったんhyperrefで素の
チェックボックスを作ってから、pikepdfで各ウィジェットの`/AP/N/Off`（黒塗り矩形）と
`/AP/N/Yes`（LuaLaTeXで個別にレンダリングした意味テキストをForm XObjectとして
差し込んだもの）を直接書き換える。`/AcroForm/NeedAppearances`をFalseにしないと
ビューアが独自に外観を再生成してカスタム外観を無視してしまう点に注意
（2026-08-19、実際にこれで一度ハマった）。

「分からなかった」の自己申告チェックボックスとは別物（同居可能、実機確認済み）。
そちらは`flashcard_render.field_name()`と同じ命名(`chk.<review_id>`)のまま、
普通のチェックマーク外観で残す。開閉用は`reveal_field_name()`(`rev.<review_id>`)。
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from academic_audio.worksheet import build_pdf, escape  # noqa: E402
from toeic_reading.flashcard_render import FlashcardEntry, field_name  # noqa: E402

__all__ = ["build_dual_checkbox_flashcards", "reveal_field_name"]

_BASE_PREAMBLE = r"""\documentclass[a4paper,10pt]{ltjsarticle}
\usepackage{luatexja}
\usepackage[margin=15mm]{geometry}
\usepackage{longtable}
\usepackage{array}
\usepackage{hyperref}
\hypersetup{hidelinks}
"""

_MEANING_PAGE = r"""\documentclass[10pt]{{ltjsarticle}}
\usepackage{{luatexja}}
\usepackage[paperwidth={width_mm}mm,paperheight={height_mm}mm,margin=0mm]{{geometry}}
\pagestyle{{empty}}
\setlength{{\parindent}}{{0pt}}
\sloppy
\begin{{document}}
\noindent\raggedright {meaning}
\end{{document}}
"""

_REVEAL_WIDTH_PT = 130.0
_REVEAL_HEIGHT_PT = 11.0
_PT_TO_MM = 25.4 / 72.0
# PDFの注釈外観は「appearance streamのBBox」から「注釈のRect」へ自動でスケーリングされる。
# 意味PDFのページ幅がRectの実幅より大きいと、その分だけ文字が縮小されて表示されてしまう
# （2026-08-19、実際に訳の文字だけ小さく見える不具合として発覚）。ページ幅をRect幅と
# 一致させ、余計な縮小が起きないようにする。高さは表の行が自然に取る高さ(実測25pt前後)に
# 合わせた固定値を使う(1行に収まる語の場合)。
_MEANING_WIDTH_MM = _REVEAL_WIDTH_PT * _PT_TO_MM
_REVEAL_BASE_HEIGHT_PT = 24.9  # 訳が1行に収まるときの行の高さ(実測)
_REVEAL_LINE_HEIGHT_PT = 13.0  # 訳が2行目以降に折り返すたびに追加する高さ(10pt文字+行間の実測目安)

# 訳の文字幅の概算。全角(かな/漢字/全角記号)は1em、それ以外(半角英数記号)は0.55emとして
# 折り返し行数を見積もる(実際にLuaLaTeXで組む前にPythonだけで概算する。実測ではなく
# 見積もりなので、大きめに出て損はないが小さく出て文字が箱からはみ出るのは避けたいため、
# 使える幅に少し余裕(0.9倍)を持たせてある)。
def _is_wide_char(ch: str) -> bool:
    cp = ord(ch)
    return (
        0x3000 <= cp <= 0x30FF  # CJK記号・ひらがな・カタカナ
        or 0x3400 <= cp <= 0x4DBF  # CJK拡張A
        or 0x4E00 <= cp <= 0x9FFF  # CJK統合漢字
        or 0xFF00 <= cp <= 0xFFEF  # 全角英数・記号
    )


def _estimate_wrapped_line_count(text: str, width_pt: float, font_size_pt: float = 10.0) -> int:
    usable_pt = width_pt * 0.9
    line_width_pt = 0.0
    lines = 1
    for ch in text:
        char_width_pt = font_size_pt * (1.0 if _is_wide_char(ch) else 0.55)
        if line_width_pt + char_width_pt > usable_pt and line_width_pt > 0:
            lines += 1
            line_width_pt = char_width_pt
        else:
            line_width_pt += char_width_pt
    return lines


def _reveal_row_height_pt(meaning: str) -> float:
    """訳の折り返し行数から、開閉ボックス(≒行全体)に必要な高さを見積もる。"""
    lines = _estimate_wrapped_line_count(meaning, _REVEAL_WIDTH_PT)
    return _REVEAL_BASE_HEIGHT_PT + max(0, lines - 1) * _REVEAL_LINE_HEIGHT_PT


def reveal_field_name(review_id: str) -> str:
    return f"rev.{review_id}"


@dataclass(frozen=True)
class _BuildPaths:
    workdir: Path
    base_tex: Path
    base_pdf: Path
    meanings_dir: Path
    out_pdf: Path


def _render_base_tex(title: str, entries: list[FlashcardEntry]) -> str:
    lines = [
        _BASE_PREAMBLE,
        r"\title{" + escape(title) + "}",
        r"\date{}",
        r"\begin{document}",
        r"\maketitle",
        "黒塗りをクリックすると意味が表示されます（もう一度クリックで戻ります）。"
        "分からなかった単語は右のチェックボックスにチェックを入れてください。",
        r"\bigskip",
        "",
        r"\begin{Form}",
        # 列を固定幅にすることで、単語の長さに関わらず「開閉ボックス」と
        # 「分からなかったチェック」が全行で同じ横位置に揃う
        # （2026-08-19、単語ごとに黒塗りの開始位置がずれる指摘を受けて表形式に変更）。
        r"\begin{longtable}{@{} r @{\hspace{4pt}} p{58mm} @{\hspace{6pt}} l @{\hspace{10pt}} l @{}}",
    ]
    for index, entry in enumerate(entries, start=1):
        # 訳が長くて1行に収まらない語は、その分だけ開閉ボックスの高さを増やす
        # （2026-08-20、訳が横に切れて読めない指摘を受けて対応。高さの見積もりは
        # _reveal_row_height_pt 参照）。CheckBoxのheightオプションは行の自然な高さの
        # 下限にしかならないため、これを大きくすれば行自体もその分だけ縦に伸びる。
        row_height_pt = _reveal_row_height_pt(entry.meaning)
        checkbox_height_pt = _REVEAL_HEIGHT_PT + (row_height_pt - _REVEAL_BASE_HEIGHT_PT)
        lines.append(
            rf"{index}. & \textbf{{{escape(entry.word)}}} & "
            + r"\CheckBox[name=" + reveal_field_name(entry.review_id)
            + rf",width={_REVEAL_WIDTH_PT}pt,height={checkbox_height_pt:.2f}pt,bordercolor=0 0 0]{{}}"
            + r" & 分からなかった\ "
            + r"\CheckBox[name=" + field_name(entry.review_id)
            + r",width=7pt,height=7pt,bordercolor=0 0 0]{} \\[7pt]"
        )
    lines.append(r"\end{longtable}")
    lines.append(r"\end{Form}")
    lines.append(r"\end{document}")
    return "\n".join(lines) + "\n"


def _run_latexmk(tex_path: Path) -> Path:
    command = [
        "latexmk", "-lualatex", "-interaction=nonstopmode", "-halt-on-error",
        f"-outdir={tex_path.parent}", f"-auxdir={tex_path.parent}", str(tex_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    pdf_path = tex_path.with_suffix(".pdf")
    if completed.returncode != 0 or not pdf_path.exists():
        raise RuntimeError(f"latexmk failed for {tex_path}:\n{completed.stdout}\n{completed.stderr}")
    return pdf_path


def build_dual_checkbox_flashcards(
    title: str, entries: list[FlashcardEntry], workdir: Path,
) -> Path:
    """開閉用チェックボックス＋自己申告チェックボックスを両方持つ単語帳PDFを組む。

    entriesが多いと、語ごとに個別のLuaLaTeXコンパイルを1回ずつ行うため時間がかかる
    （目安: 1語あたり1〜2秒）。数千語規模で使う場合はバッチ化を検討すること
    （現状は試作段階のため未最適化）。
    """
    import pikepdf
    from pikepdf import Array, Dictionary, Name, Pdf

    workdir.mkdir(parents=True, exist_ok=True)
    meanings_dir = workdir / "meanings"
    meanings_dir.mkdir(exist_ok=True)

    base_tex = workdir / "base.tex"
    base_tex.write_text(_render_base_tex(title, entries), encoding="utf-8")
    base_pdf = _run_latexmk(base_tex)

    meaning_pdfs: dict[str, Path] = {}
    for index, entry in enumerate(entries, start=1):
        tex_path = meanings_dir / f"m{index:04d}.tex"
        # 素の "/" はLaTeXの行分割候補にならず、区切りに"/"を多用する訳(例:
        # 「参照する/言及する」)が折り返せずに箱からはみ出すことがある。\slashなら
        # 見た目は"/"のまま、直後での改行を許可できる。
        meaning_text = escape(entry.meaning).replace("/", r"\slash{}")
        row_height_pt = _reveal_row_height_pt(entry.meaning)
        tex_path.write_text(
            _MEANING_PAGE.format(
                meaning=meaning_text,
                width_mm=f"{_MEANING_WIDTH_MM:.2f}",
                height_mm=f"{row_height_pt * _PT_TO_MM:.2f}",
            ),
            encoding="utf-8",
        )
        meaning_pdfs[entry.review_id] = _run_latexmk(tex_path)

    base = Pdf.open(base_pdf)
    base.Root.AcroForm.NeedAppearances = False
    by_field = {reveal_field_name(e.review_id): e for e in entries}
    mark_fields = {field_name(e.review_id) for e in entries}

    for page in base.pages:
        annots = page.get("/Annots")
        if not annots:
            continue
        for annot in annots:
            if annot.get("/Subtype") != Name.Widget:
                continue
            field = str(annot.get("/T", ""))
            rect = annot.Rect
            x0, y0, x1, y1 = (float(v) for v in rect)
            w, h = x1 - x0, y1 - y0

            entry = by_field.get(field)
            if entry is not None:
                src = Pdf.open(meaning_pdfs[entry.review_id])
                fx = base.copy_foreign(src.pages[0].as_form_xobject())
                src.close()

                # \CheckBox の height オプションは、テーブル行の実際の高さより小さくできない
                # （行の自然な高さに引き伸ばされる。2026-08-19確認）。行同士の黒塗りが
                # くっついて1枚の板に見えないよう、矩形の上下を少し内側に縮めて描画する。
                margin = min(3.0, h * 0.12)
                off_stream = base.make_stream(
                    f"0 0 0 rg 0 {margin:.2f} {w:.2f} {(h - 2 * margin):.2f} re f\n".encode()
                )
                off_stream.BBox = Array([0, 0, w, h])
                off_stream.Resources = Dictionary()
                off_stream.Type = Name.XObject
                off_stream.Subtype = Name.Form

                ap = Dictionary()
                n = Dictionary()
                n.Off = off_stream
                n.Yes = fx
                ap.N = n
                annot.AP = ap
                annot.AS = Name.Off
            elif field in mark_fields:
                # 「分からなかった」チェックも同じ理由(行の高さへの引き伸ばし)で
                # 縦長の箱に見えてしまうため、Rectの中央に小さい正方形だけを描く
                # カスタム外観に差し替える(既定のチェックマーク外観は使わない)。
                size = min(8.0, w, h)
                # 行の幾何学的な中央(h/2)に置くと、テキストの基準線(baseline)より
                # 少し下にズレて見える(行の上側の空き=leadingの方が下側より大きいため)。
                # 「分からなかった」の文字位置に視覚的に揃うよう、少し上へオフセットする
                # （2026-08-20、実機で下ズレを指摘されて調整）。
                cx, cy = w / 2, h / 2 + 2.5
                x = cx - size / 2
                y = cy - size / 2
                off_stream = base.make_stream(
                    f"0 0 0 RG 0.8 w {x:.2f} {y:.2f} {size:.2f} {size:.2f} re S\n".encode()
                )
                off_stream.BBox = Array([0, 0, w, h])
                off_stream.Resources = Dictionary()
                off_stream.Type = Name.XObject
                off_stream.Subtype = Name.Form

                yes_stream = base.make_stream(
                    f"0 0 0 rg {x:.2f} {y:.2f} {size:.2f} {size:.2f} re f\n".encode()
                )
                yes_stream.BBox = Array([0, 0, w, h])
                yes_stream.Resources = Dictionary()
                yes_stream.Type = Name.XObject
                yes_stream.Subtype = Name.Form

                ap = Dictionary()
                n = Dictionary()
                n.Off = off_stream
                n.Yes = yes_stream
                ap.N = n
                annot.AP = ap
                annot.AS = Name.Off

    out_pdf = workdir / "flashcards-reveal.pdf"
    base.save(out_pdf)
    return out_pdf
