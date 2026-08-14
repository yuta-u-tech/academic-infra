"""生成物のスキーマ。Pydantic モデルを正とし、JSON Schema はそこから吐く。

生成物には必ず出所（`review_id` / `source_commit`）と生成理由・生成者・プロンプト版を
持たせる。後から「なぜこの問題が作られたか」「どの版の資料から作られたか」を再現できないと、
資料が更新されたときに古い問題を捨てる判断ができなくなるため。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "english" / "schema"

VOCAB_SUB_SKILLS = ("recognition", "recall", "usage", "collocation", "countability")
READING_SUB_SKILLS = ("comprehension", "syntax_parsing", "vocabulary", "reading_speed")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VocabItem(_Strict):
    """専門語彙カード。goigoi の word.schema.json v1 へ写せる形に揃えてある。"""

    kind: Literal["vocab"] = "vocab"
    domain: Literal["vocabulary"] = "vocabulary"
    sub_skill: Literal["recognition", "recall", "usage", "collocation", "countability"] = "recall"
    word: str = Field(min_length=1, max_length=200)
    meaning: str = Field(min_length=1, max_length=1000)
    example: str | None = Field(default=None, max_length=1000)
    part_of_speech: str | None = Field(default=None, max_length=40)
    collocations: list[str] = Field(default_factory=list, max_length=10)

    def prompt(self) -> str:
        return self.word

    def check(self, response: str) -> bool:
        return response.strip().casefold() == self.word.strip().casefold()


class ReadingItem(_Strict):
    """英文読解の選択式問題。"""

    kind: Literal["reading"] = "reading"
    domain: Literal["reading"] = "reading"
    sub_skill: Literal["comprehension", "syntax_parsing", "vocabulary", "reading_speed"] = (
        "comprehension"
    )
    passage: str = Field(min_length=1, max_length=4000)
    question: str = Field(min_length=1, max_length=500)
    choices: list[str] = Field(min_length=2, max_length=6)
    answer_index: int = Field(ge=0)
    explanation: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def _answer_in_range(self) -> "ReadingItem":
        if self.answer_index >= len(self.choices):
            raise ValueError(
                f"answer_index={self.answer_index} は choices({len(self.choices)}件)の範囲外です。"
            )
        return self

    def prompt(self) -> str:
        return self.question

    def check(self, response: str) -> bool:
        try:
            return int(response) == self.answer_index
        except (TypeError, ValueError):
            return False


class ListeningItem(_Strict):
    """TOEICリスニング（Part2/3/4）の選択式設問。

    音声そのものはこのDBに複製しない（正本は academic-english-data / YouTube）。
    ここには出題文・選択肢・正解・解説だけを持つ（`passage` はリスニングには無いので
    ReadingItem とは分けて別のkindにする）。
    """

    kind: Literal["listening"] = "listening"
    domain: Literal["listening"] = "listening"
    sub_skill: Literal["part2", "part3", "part4"] = "part2"
    question: str = Field(min_length=1, max_length=1000)
    choices: list[str] = Field(min_length=2, max_length=6)
    answer_index: int = Field(ge=0)
    explanation: str = Field(min_length=1, max_length=2000)
    # 聞き取りの難所(リンキング・リダクション等)の解説。academic_audio側の
    # PassageQuestion/ListeningItem.pronunciation_note をそのまま持ち込む。
    # 過去に取り込んだセットには無いので省略可。
    pronunciation_note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _answer_in_range(self) -> "ListeningItem":
        if self.answer_index >= len(self.choices):
            raise ValueError(
                f"answer_index={self.answer_index} は choices({len(self.choices)}件)の範囲外です。"
            )
        return self

    def prompt(self) -> str:
        return self.question

    def check(self, response: str) -> bool:
        try:
            return int(response) == self.answer_index
        except (TypeError, ValueError):
            return False


class GrammarItem(_Strict):
    """空所補充の文法問題（TOEIC Part 5 の形）。

    読解と分けているのは、誤答原因の分岐が違うため。読解の誤りは「文が読めていない」
    かもしれないが、1文の空所補充を外すのは文法知識そのものの問題に絞り込める。
    """

    kind: Literal["grammar"] = "grammar"
    domain: Literal["grammar"] = "grammar"
    sub_skill: Literal["knowledge", "recognition", "production", "processing_speed"] = "knowledge"
    sentence: str = Field(min_length=1, max_length=600, description="空所は ____ で示す")
    choices: list[str] = Field(min_length=3, max_length=5)
    answer_index: int = Field(ge=0)
    explanation: str = Field(min_length=1, max_length=2000)
    point: str = Field(min_length=1, max_length=120, description="問われている文法項目")
    pattern: Literal["A", "B", "C"] = Field(
        description="誤答選択肢の作り方（english/prompts/grammar.md参照）: "
        "A=同じ語の別の形 / B=似ているが別の語 / C=コロケーション知識"
    )
    pattern_note: str = Field(
        min_length=1, max_length=300, description="このpatternに分類した理由"
    )

    @model_validator(mode="after")
    def _blank_and_answer_are_consistent(self) -> "GrammarItem":
        if "____" not in self.sentence:
            raise ValueError("sentence に空所 '____' がありません。")
        if self.answer_index >= len(self.choices):
            raise ValueError(
                f"answer_index={self.answer_index} は choices({len(self.choices)}件)の範囲外です。"
            )
        return self

    def prompt(self) -> str:
        return self.sentence

    def check(self, response: str) -> bool:
        try:
            return int(response) == self.answer_index
        except (TypeError, ValueError):
            return False


class ReadingBlankItem(_Strict):
    """長文中の空所補充（TOEIC Part 6 の形）。

    GrammarItem（Part5）の point/pattern による誤答傾向追跡と、ReadingItem（Part7）の
    passageグルーピングを合成したもの。1つのpassageに空所が4つぶら下がり、うち1つは
    単語/句選択ではなく「文挿入」（blank_type="sentence"）になる。文挿入はA/B/Cの
    誤答パターン分類が馴染まないため pattern/pattern_note は省略可にしてある。
    """

    kind: Literal["reading_blank"] = "reading_blank"
    domain: Literal["reading"] = "reading"
    sub_skill: Literal["comprehension", "syntax_parsing", "vocabulary", "reading_speed"] = (
        "comprehension"
    )
    passage: str = Field(min_length=1, max_length=4000, description="空所は [1]〜[4] で示す")
    blank_number: int = Field(ge=1, le=4)
    blank_type: Literal["word", "sentence"] = "word"
    choices: list[str] = Field(min_length=3, max_length=5)
    answer_index: int = Field(ge=0)
    explanation: str = Field(min_length=1, max_length=2000)
    point: str = Field(min_length=1, max_length=120, description="問われている文法/語彙項目")
    pattern: Literal["A", "B", "C"] | None = Field(
        default=None,
        description="誤答選択肢の作り方（english/prompts/grammar.md参照）。blank_type=wordのみ必須",
    )
    pattern_note: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _blank_marker_and_answer_are_consistent(self) -> "ReadingBlankItem":
        marker = f"[{self.blank_number}]"
        if marker not in self.passage:
            raise ValueError(f"passage に空所マーカー '{marker}' がありません。")
        if self.answer_index >= len(self.choices):
            raise ValueError(
                f"answer_index={self.answer_index} は choices({len(self.choices)}件)の範囲外です。"
            )
        return self

    def prompt(self) -> str:
        return f"{self.passage}\n\n[{self.blank_number}]"

    def check(self, response: str) -> bool:
        try:
            return int(response) == self.answer_index
        except (TypeError, ValueError):
            return False


Item = Annotated[
    Union[VocabItem, ReadingItem, GrammarItem, ListeningItem, ReadingBlankItem],
    Field(discriminator="kind"),
]


class GeneratedItem(_Strict):
    """1件の生成物と、その出所・理由。"""

    difficulty: int = Field(ge=1, le=5)
    reason: str = Field(min_length=1, max_length=500, description="なぜこの問題を生成したか")
    item: Item


class GenerationResult(_Strict):
    """Claude が1回の生成で書き出すファイルの全体。

    `source_commit` は資料側の manifest の commit をそのまま転記する。資料が更新されて
    commit が変われば、この生成物は「古い版から作られたもの」と判定できる。
    """

    schema_version: Literal[1] = 1
    review_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    source_commit: str = Field(min_length=1)
    generated_by: str = Field(min_length=1, description="例: claude-opus-5")
    prompt_version: str = Field(min_length=1, description="english/prompts/*.md の版")
    is_ephemeral: bool = Field(default=True, description="検証前の一時生成物か")
    items: list[GeneratedItem] = Field(min_length=1, max_length=50)


def write_json_schemas(destination: Path = SCHEMA_DIR) -> list[Path]:
    """Pydantic モデルから JSON Schema を書き出す（人間とAIが仕様を読むため）。"""
    destination.mkdir(parents=True, exist_ok=True)
    written = []
    for name, model in (("generation-result", GenerationResult),):
        path = destination / f"{name}.schema.json"
        path.write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return written
