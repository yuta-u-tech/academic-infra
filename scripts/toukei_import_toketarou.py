#!/usr/bin/env python3
"""statisticsschool.com 問題集(.tex)を toukei_study のDBへ取り込む一回限りの変換スクリプト。

ユーザーのDesktopにある `problems_statistics_applied.tex`（統計検定準1級レベル 全240問、
`\\ptitle{番号}{タイトル}{難易度}` + problemcard/answerbox/explainbox 形式）から
選択式問題（A〜E）だけを抽出し、`\\section{...}` の分野名をacinfra_coreの4 Competencyへ
マッピングして toukei.db に取り込む。数式・説明文はLaTeXコマンドを軽く平文化するだけで、
$...$ の数式はそのまま残す（読める前提の個人利用ツールのため）。

    python3 scripts/toukei_import_toketarou.py --tex ~/Desktop/.../problems_statistics_applied.tex
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from toukei_study.db import connect  # noqa: E402
from toukei_study.study import ingest_problems  # noqa: E402

SECTION_TO_COMPETENCY = {
    "確率と確率分布": "toukei.probability_distribution",
    "極限・漸近理論": "toukei.probability_distribution",
    "統計的推測（推定）": "toukei.statistical_inference",
    "統計的推測（検定）": "toukei.statistical_inference",
    "回帰分析": "toukei.multivariate_analysis",
    "多変量解析": "toukei.multivariate_analysis",
    "確率過程": "toukei.applications",
    "時系列解析": "toukei.applications",
    "ベイズ統計学": "toukei.applications",
    "モデル選択・評価": "toukei.applications",
    "標本調査法": "toukei.applications",
    "実験計画法": "toukei.applications",
}

_LETTER_TO_INDEX = {letter: index for index, letter in enumerate("ABCDE")}


def _clean_latex(text: str) -> str:
    text = text.replace("\\%", "%")
    text = re.sub(r"\\textbf\{([^}]*)\}", r"**\1**", text)
    text = re.sub(r"\\(begin|end)\{(itemize|quote|center)\}", "", text)
    text = re.sub(r"\\item\s*", "- ", text)
    text = text.replace("\\medskip", "").replace("\\par", "\n").replace("\\\\", "\n")
    text = re.sub(r"\\(toprule|midrule|bottomrule)", "", text)
    text = re.sub(r"\\renewcommand\{\\arraystretch\}\{[^}]*\}", "", text)
    text = re.sub(r"\\begin\{tabularx\}\{[^}]*\}\{[^}]*\}", "", text)
    text = text.replace("\\end{tabularx}", "")
    text = text.replace("&", " | ")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_answer_index(answerbox_text: str) -> int | None:
    match = re.search(r"正答\}\\quad\s*([A-E])\.", answerbox_text)
    if not match:
        return None
    return _LETTER_TO_INDEX[match.group(1)]


def _extract_choices(problemcard_text: str) -> list[str] | None:
    match = re.search(
        r"\\begin\{enumerate\}\[label=\\Alph\*\.\](.*?)\\end\{enumerate\}", problemcard_text, re.DOTALL
    )
    if not match:
        return None
    items = re.split(r"\\item\s*", match.group(1))
    choices = [_clean_latex(item).strip() for item in items if item.strip()]
    return choices or None


def parse_problems(tex_path: Path) -> list[dict]:
    content = tex_path.read_text(encoding="utf-8")

    section_positions = [(m.start(), m.group(1)) for m in re.finditer(r"\\section\{([^}]*)\}", content)]

    def section_for(offset: int) -> str | None:
        current = None
        for pos, name in section_positions:
            if pos <= offset:
                current = name
            else:
                break
        return current

    headers = list(re.finditer(r"\\ptitle\{(\d+)\}\{([^}]*)\}\{(\d+)\}", content))
    problems: list[dict] = []
    for index, header in enumerate(headers):
        start = header.end()
        end = headers[index + 1].start() if index + 1 < len(headers) else len(content)
        block = content[start:end]
        section = section_for(header.start())
        competency_id = SECTION_TO_COMPETENCY.get(section)
        if competency_id is None:
            continue

        card_match = re.search(r"\\begin\{problemcard\}(.*?)\\end\{problemcard\}", block, re.DOTALL)
        answer_match = re.search(r"\\begin\{answerbox\}(.*?)\\end\{answerbox\}", block, re.DOTALL)
        explain_match = re.search(r"\\begin\{explainbox\}(.*?)\\end\{explainbox\}", block, re.DOTALL)
        if not (card_match and answer_match):
            continue

        card_text = card_match.group(1)
        choices = _extract_choices(card_text)
        if choices is None:
            continue  # 選択式でない（記述式）問題はこのquiz形式では出題しないためスキップ

        question_match = re.search(
            r"問題文\}\\par(.*?)\\medskip\\textbf\{選択肢\}", card_text, re.DOTALL
        )
        if not question_match:
            continue
        question = _clean_latex(question_match.group(1))

        answer_index = _extract_answer_index(answer_match.group(1))
        if answer_index is None or answer_index >= len(choices):
            continue

        explanation = ""
        if explain_match:
            explanation = _clean_latex(re.sub(r"^\s*解説\}\\par", "", explain_match.group(1)))
        # 解説は数千文字に及ぶことがあるため、ターミナル出題では長すぎる。冒頭だけ残す。
        if len(explanation) > 1200:
            explanation = explanation[:1200] + "\n…（以下略。元の問題集PDFで全文確認）"

        problems.append(
            {
                "competency_id": competency_id,
                "question": question,
                "choices": choices,
                "answer_index": answer_index,
                "explanation": explanation or "(解説なし)",
                "source_title": header.group(2),
                "level": header.group(3),
                "source_file": str(tex_path),
                # \ptitle{N}のNはセクション内で1〜20に振り直され全体ではユニークでないため、
                # 出現順のグローバル連番を使う（render.extract_raw_blocksと同じ採番規則）。
                "source_number": index + 1,
            }
        )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tex", type=Path, required=True)
    parser.add_argument("--set-id", default="toketarou-statisticsschool", dest="set_id")
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args()

    problems = parse_problems(args.tex)
    by_competency: dict[str, list[dict]] = {}
    for problem in problems:
        by_competency.setdefault(problem["competency_id"], []).append(problem)

    with connect(args.db) as connection:
        summary = {}
        for competency_id, items in by_competency.items():
            inserted = ingest_problems(connection, args.set_id, competency_id, items)
            summary[competency_id] = inserted

    total = sum(summary.values())
    print(f"取り込み完了: {total}問")
    for competency_id, count in sorted(summary.items()):
        print(f"  {competency_id}: {count}問")
    return 0


if __name__ == "__main__":
    sys.exit(main())
