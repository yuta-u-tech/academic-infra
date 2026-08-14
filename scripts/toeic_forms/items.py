"""Forms 化する問題データのスキーマ。

toeic_reading や academic_audio の各アイテム型（GrammarItem 等）とは独立させてある。
Forms 組み立ては出題形式（choice/free）だけを見て動くので、Part5/Part7/リスニングの
どの生成元から来たかに関わらず同じ形に正規化してから渡す。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChoiceFormItem(_Strict):
    kind: Literal["choice"] = "choice"
    review_id: str = Field(min_length=1, max_length=200)
    topic: str = Field(min_length=1, max_length=100)
    difficulty: int = Field(ge=1, le=5)
    question: str = Field(min_length=1, max_length=2000)
    choices: list[str] = Field(min_length=2, max_length=6)
    answer_index: int = Field(ge=0)
    explanation: str = Field(min_length=1, max_length=2000)
    # TOEIC Part1(写真描写)専用。設問の上に写真を表示する(Google Forms公開URL、
    # `academic_audio.part1_images.publish_to_drive()`が発行したもの)。他の形式では省略。
    image_url: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _answer_in_range(self) -> "ChoiceFormItem":
        if self.answer_index >= len(self.choices):
            raise ValueError(
                f"answer_index={self.answer_index} は choices({len(self.choices)}件)の範囲外です。"
            )
        return self


class FreeFormItem(_Strict):
    kind: Literal["free"] = "free"
    review_id: str = Field(min_length=1, max_length=200)
    topic: str = Field(min_length=1, max_length=100)
    difficulty: int = Field(ge=1, le=5)
    question: str = Field(min_length=1, max_length=2000)
    model_answer: str = Field(min_length=1, max_length=2000)
    explanation: str = Field(min_length=1, max_length=2000)


SELF_GRADE_OPTIONS = ("合っていた", "部分的に合っていた", "違った")
