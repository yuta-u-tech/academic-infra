---
id: toeic-part2
name: TOEIC Part 2（応答問題）
engine: piper
language: en
speakers: 1
answer_in_audio: true
item:
  - role: question
    count: 1
    words: [6, 15]
    pause: 0.6
  - role: choice
    count: 3
    words: [4, 12]
    pause: 0.5
---

# TOEIC Part 2 形式のリスニング問題

質問または発言が1つ読まれ、それに対する応答3つのうち最も適切なものを選ぶ。
**本番同様、応答(A)(B)(C)は音声でのみ読まれ、冊子には印刷しない**
（`answer_in_audio: true`）。正解・解説は問題冊子（TeX）側の解答ページに出す。

`Number N.` の通し番号読み上げ、選択肢間の間隔（約1秒）、次の問題までのマーク時間
（約5秒）は `items.py: to_script()` が自動で付与する。作問側（Claude）は
`question`/`choice` の本文だけを書けばよい。

狙いは特定分野の内容理解ではなく、**TOEIC本番と同じ日常ビジネスの場面を英語で
聴き取れること**。題材は資料の分野に縛らない（[toeic-topics.md](../prompts/toeic-topics.md)
参照）。資料と結びつけるのは語彙（`vocabulary`）だけでよい。

## 質問文（`question`）の型

Part 2 の質問は疑問詞疑問文が中心で、そこに平叙文・付加疑問・選択疑問が混ざる。
**同じ型を3問以上続けない。**

| 型 | 例 |
|---|---|
| WH疑問文 | `When will the shipment arrive?` |
| Yes/No疑問文 | `Have you finished reviewing the budget report?` |
| 平叙文（依頼・提案） | `We should double-check the meeting schedule.` |
| 選択疑問文 | `Should we book the conference room or meet online?` |
| 付加疑問 | `The order was shipped yesterday, wasn't it?` |

WH疑問文は **冒頭の疑問詞を聴き取れるかが勝負**なので、疑問詞の直後に長い修飾を
置かない。`When, after the team has finished, will ...` のような文は作らない。

## 応答（`choice`）の作り方

3つのうち1つが正解、2つが誤答。**誤答は「聴き違えたら選んでしまう」もの**にする。
ランダムな無関係文を混ぜない。Part 2 の誤答は型が決まっている。

| 誤答の型 | 何を突くか | 例（質問が `When will the report be ready?`） |
|---|---|---|
| 音の似た語 | `report` / `reporter`、`where` / `wear` | `The reporter is in the meeting.` |
| 疑問詞の取り違え | When を Where と聴いた人が選ぶ | `In the second building.` |
| 関連語の連想 | 話題は合っているが応答になっていない | `The results were quite accurate.` |

1問につき誤答の型は**2つとも違うものを使う**。同じ型を2つ並べると消去法で解けてしまう。

## `vocabulary` が依頼に含まれる場合

`--vocab-deck` で study-forge（金フレ由来）の語彙が混ぜてある場合、依頼 JSON に
`vocabulary.terms` が入る。**全語を無理に使わない。** 選んだシナリオに馴染むものだけを、
質問文か応答のどこかで自然に使う。使わなかった語があってよい。

語を出す場所は選べる。誤答の「音の似た語」に使うのも有効（`vocabulary` の語と語幹が
近い語をこちらで作る）。どの語をどう使ったかは `reason` に書く。

## 正解にしてよい応答

- 直接答える: `By Friday afternoon.`
- 答えられないと言う: `I haven't checked with the team yet.`
- 質問で返す: `Do you need it before the review?`

**「答えられない」型と質問返し型を必ず混ぜる。** 直接答える形ばかりだと、
内容を聴かずに「それらしい答え」を選ぶ癖がつく。全体の3割程度をこの2型にする。

## 話者について

Piper は1ジョブ1音声モデルなので、質問と応答が同じ声になる。実際の試験とは違うが、
Part 2 は話者の性別が解答根拠にならないため学習上は問題ない。

**応答に `Man:` `Woman:` のような話者ラベルを書かない。** そのまま読み上げられる。

## 語数

`question` は 6〜15語、`choice` は 4〜12語。これを超えると Part 2 らしくなくなり、
短すぎると聴解の負荷が無くなる。

## 解説（`explanation`）

**なぜ他の2つが違うか**まで書く。日本語で書く。誤答をどの型で作ったかを明示すると、
学習者が自分の誤答傾向を掴める。

> 正解は (A)。`When` で時期を聞いているので時間表現で答える。
> (B) は場所を答えており、`When` を `Where` と聴き違えた場合に選ぶ。
> (C) は `report` と音の似た `reporter` に引かれた誤答。

## reason

なぜこの問題を作ったか。どのシナリオ分類を選んだか、`vocabulary` を使った場合は
どの語をどう使ったかを書く。出題の偏りを後から点検するために使う。

## 制約

- 題材は資料の分野に縛られない。[toeic-topics.md](../prompts/toeic-topics.md) の
  シナリオ分類から選ぶ（本番の TOEIC も特定分野の専門知識を前提にしない）。
- 数式・記号を英文に入れない（`O(log n)` ではなく `order log n`）。
- 固有名詞は使わない。会社名・人名を覚える問題にしない。
- 1文に接続詞を2つ以上入れない。
- 正解の位置を (A)(B)(C) で偏らせない。
