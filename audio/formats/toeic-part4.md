---
id: toeic-part4
name: TOEIC Part 4（説明文問題）
engine: piper
language: en
speakers: 1
answer_in_audio: false
grouping: passage
passage:
  speakers: 1
  turns: [3, 6]
  words_per_turn: [15, 35]
questions:
  count: 3
  words: [8, 15]
  choice_count: 4
  choice_words: [3, 12]
---

# TOEIC Part 4 形式のリスニング問題

1人の話者による短い説明文（アナウンス・留守番電話・会議の一部・広告など）が読まれ、
それに続く3つの設問にそれぞれ4択で答える。選択肢は音声では読まれない
（`answer_in_audio: false`）。冊子に印刷されたものを読んで答える。

狙いは特定分野の内容理解ではなく、**TOEIC本番と同じ日常ビジネスの場面を、
まとまった英語の独白として聴いて構造を追えること**。題材は資料の分野に縛らない
（[toeic-topics.md](../prompts/toeic-topics.md) 参照）。資料と結びつけるのは
`vocabulary` だけでよい。

## `passage`（説明文）の型

話者は1人（`passage.speakers: 1`）。`speaker` フィールドは常に `"A"` にする。
3〜6発話に分け、1つの話の流れとして繋がるようにする（バラバラな文の羅列にしない）。

実際の Part 4 で使われる型を混ぜる。場面（アナウンスの中身、留守番電話の用件など）は
[toeic-topics.md](../prompts/toeic-topics.md) のシナリオ分類から選ぶ。
**資料の分野を独白の題材にしない。**

| 型 | 場面 | 冒頭の言い回し |
|---|---|---|
| アナウンス | 館内放送・イベント案内 | `Attention, please. ...` |
| 留守番電話 | 折り返し依頼・状況説明 | `Hi, this is ... calling about ...` |
| 会議の一部 | 進捗報告・方針説明 | `Before we move on, I'd like to update everyone on ...` |
| 広告 | 製品・サービスの紹介 | `Are you looking for ...?` |
| ニュース・天気 | 短い時事解説 | `In today's update, ...` |

**1つの item では1つの型に統一する。** アナウンスの途中で留守番電話の言い回しに
切り替わったりしない。

## 音声の自動付与（作問側は書かなくてよい）

`items.py: passage_to_script()` が本番同様の進行を自動で付与する。

- 説明文の前: `Questions N through M refer to the following talk.`
- 各設問: `Number N.` を単独の発話にして短い間（約0.5秒）を置いてから設問文を読む
  （冊子側の通し番号と一致。番号を認識する間もなく設問が始まって聞き逃す、という
  指摘を受けて分離した）
- 各設問の後: 約8秒のマーク時間（ETS本番と同じ長さ。「本当に尋ねている」間も兼ねる）

## 音声生成時の話者マッピング

`render` に `--piper-voice-map "A=<voice1.onnx>,narrator=<voice2.onnx>"` を渡す。
**`narrator`（設問を読む声）は `A`（説明文を話す声）と別のモデルにする。** 同じ声だと
"Number N." や設問文が説明文の続きに聞こえてしまい、どこからが設問か判別できない。

作問側（Claude）は `passage`（発話）と `questions`（設問文・選択肢・正解・解説）の
本文だけを書けばよい。

## `questions`（設問）の型

3問はそれぞれ違う観点を問う。同じ観点を2問続けない。

| 観点 | 例 |
|---|---|
| 主題・目的 | `What is the announcement mainly about?` |
| 詳細 | `What will happen next Monday?` |
| 話者の意図 | `Why does the speaker mention the budget?` |
| 依頼・提案 | `What are listeners asked to do?` |
| 場所・職業の推測 | `Where most likely does this announcement take place?` |

## 選択肢（`choices`）の作り方

4つのうち1つが正解、3つが誤答。誤答は「聴き違えたら選んでしまう」ものにする。

| 誤答の型 | 何を突くか |
|---|---|
| 音の似た語 | 説明文中の語と発音が近い別の語で作った選択肢 |
| 時制・数の取り違え | 説明文の内容を、時制や単数複数を変えて誤らせる |
| 部分的に正しい | 説明文の一部には合うが、設問が聞いている点とはズレている |
| 過度な一般化・飛躍 | 説明文からは導けない結論 |

4つの誤答の型は**そのうち3問の中で偏らせない**（毎回同じ型の誤答ばかりにしない）。

## `vocabulary` が依頼に含まれる場合

`--vocab-deck` で語彙が混ぜてある場合の扱いは
[toeic-part2.md](./toeic-part2.md#vocabulary-が依頼に含まれる場合) と同じ。
全語を無理に使わない。選んだシナリオに馴染むものだけを説明文か設問に使う。

## 語数

`passage` の各発話は15〜35語、`questions` の設問文は8〜15語、選択肢は3〜12語。

## 解説（`explanation`）

なぜ正解か、他の3つがなぜ誤答かを日本語で書く。誤答をどの型で作ったかを明示する。

## 制約

- 題材は資料の分野に縛られない。[toeic-topics.md](../prompts/toeic-topics.md) の
  シナリオ分類から選ぶ。
- 数式・記号を英文に入れない。
- 固有名詞・会社名・人名は使わない。
- 1発話に接続詞を2つ以上入れない。
- 正解の位置を (A)〜(D) で偏らせない。3問中に同じ記号が2回以上正解にならないようにする。
