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

`Number N.` の通し番号読み上げ（質問文の前に短い間・約0.5秒を置いて分けて読む。番号を
認識する間もなく質問が始まって聞き逃す、という指摘を受けて分離した）、疑問文の後の
「本当に尋ねている」間（約1.2秒）、各応答の前の `A.` `B.` `C.` 読み上げ、次の問題までの
マーク時間（約5秒）は `items.py: to_script()` が自動で付与する。作問側（Claude）は
`question`/`choice` の本文だけを書けばよい（記号は書かない）。

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

`items.py: to_script()` は質問（`Number N.` + 質問文）を `speaker="narrator"`、
3つの応答をまとめて `speaker="respondent"` で出す。**本番は全て同じナレーターの声だが、
学習用にどちらを読んでいるか声で分かるよう意図的に声を分けている。**

`render` には `--piper-voice-map "narrator=<voice1.onnx>,respondent=<voice2.onnx>"`
を渡す（Part 3/4 と同じ仕組み）。単一 `--piper-model` は使わない。

応答3つは1回の音声合成にまとめて出す（別々に合成して無音でつなぐと、文と文の
つながりの抑揚が失われて棒読みに聞こえるため）。**応答に `Man:` `Woman:` のような
話者ラベルを書かない。** そのまま読み上げられる。

## 語数

`question` は 6〜15語、`choice` は 4〜12語。これを超えると Part 2 らしくなくなり、
短すぎると聴解の負荷が無くなる。

## 解説（`explanation`）

**なぜ他の2つが違うか**まで書く。日本語で書く。誤答をどの型で作ったかを明示すると、
学習者が自分の誤答傾向を掴める。

これに加えて、**聞き取りにくくなりやすい箇所の実際の読まれ方**を必ず1箇所以上指摘する。
「聞き取れなかった」を「発音自体を知らなかった／リンキングを捉えられなかった／
省略・弱形を認知できなかった」のどれかに切り分けられるよう、種類を明示する。

| 種類 | 何が起きるか | 例 |
|---|---|---|
| リンキング（連結） | 語末の子音と次の語頭の母音がつながる | `check it out` → 「チェッキラウ」 |
| 脱落 | 語末の破裂音（t/d等）が次の子音の前で消える | `next to` → 「ネクストゥ」ではなく「ネクストゥ」の t がほぼ聞こえない |
| 弱形発音 | 機能語（to/for/can/that等）が弱く短く読まれる | `to` → /tə/、`can` → /kən/ |
| 同化 | 隣り合う音が混ざって別の音に聞こえる | `did you` → 「ディジュ」 |

質問文・応答のうち実際にこれが起きそうな語句を具体的に引用して書く。

> 正解は (A)。`When` で時期を聞いているので時間表現で答える。
> (B) は場所を答えており、`When` を `Where` と聴き違えた場合に選ぶ。
> (C) は `report` と音の似た `reporter` に引かれた誤答。
> 聞き取りのポイント: `will the` は「ウィル・ザ」ではなく連結して「ウィルザ」に近く聞こえる
> （リンキング）。`report` の語尾 `t` も次が子音のときはほぼ脱落する。

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
