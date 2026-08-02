---
id: toeic-part3
name: TOEIC Part 3（会話問題）
engine: piper
language: en
speakers: 2
answer_in_audio: false
grouping: passage
passage:
  speakers: 2
  turns: [4, 8]
  words_per_turn: [10, 25]
questions:
  count: 3
  words: [8, 15]
  choice_count: 4
  choice_words: [3, 12]
---

# TOEIC Part 3 形式のリスニング問題

2人の会話が読まれ、それに続く3つの設問にそれぞれ4択で答える。選択肢は音声では
読まれない（`answer_in_audio: false`）。冊子に印刷されたものを読んで答える。

音声は話者ごとに別の Piper 音声モデルで生成される（`--piper-voice-map`）。
学習者が声だけで話者を聴き分けられることが前提の形式なので、**`speaker` を
`"A"` `"B"` で一貫させ、途中で入れ替えない。**

## `passage`（会話）の型

`passage.speakers: 2`。`speaker` は `"A"` と `"B"` の2種類のみ使う。4〜8発話、
1つの用件について話す自然な会話にする（無関係な話題を並べない）。

会話は**用件が進展する**形にする。「同じことの言い換え」の往復にしない。

```
A: 依頼・報告・問題提起
B: 応答・確認・追加情報
A: 深掘り・条件の提示
B: 合意・代案・懸念
```

実際の Part 3 で使われる場面を混ぜる。

| 場面 | 典型的な用件 |
|---|---|
| オフィスの会話 | 予定変更、資料の確認依頼、承認待ち |
| 店舗・サービス | 注文の変更、在庫確認、予約の調整 |
| 技術的な打ち合わせ | 不具合の報告、仕様の確認、対応方針 |
| 出張・移動 | 予定の調整、交通手段、宿泊 |

**1つの item では1つの用件に統一する。** 途中で無関係な話題に飛ばない。

## `questions`（設問）の型

3問はそれぞれ違う観点を問う。同じ観点を2問続けない。

| 観点 | 例 |
|---|---|
| 主題 | `What are the speakers mainly discussing?` |
| 話者の役割・場所 | `Where does the woman most likely work?` |
| 次の行動 | `What will the man probably do next?` |
| 問題点 | `What problem does the woman mention?` |
| 話者の意図 | `What does the man mean when he says "..."?`（発言引用は短く） |

## 選択肢の作り方・語彙・解説・制約

[toeic-part4.md](./toeic-part4.md) と同じ方針を使う（誤答の型、`vocabulary` の扱い、
語数、`explanation` の書き方、正解位置の偏り防止）。会話特有の点だけ以下に足す。

- 「話者の意図」を問う設問では、選択肢を発言の字面ではなく**意図の解釈**で作る
  （字面が同じ選択肢を混ぜない）。
- 「次の行動」を問う設問の正解は、**会話の最後の発話に対応させる**。会話の途中に
  出てきただけの行動を正解にしない。

## 音声生成時の話者マッピング

`render` に `--piper-voice-map "A=<voice1.onnx>,B=<voice2.onnx>,narrator=<voice1.onnx>"`
を渡す。`narrator` は設問を読む声（`A` と同じモデルでよい）。3人以上の会話は現状
未対応（`passage.speakers` は最大3だが、Piper の声質バリエーションが限られるため
実運用は2人を基本にする）。
