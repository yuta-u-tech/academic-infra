# 空所補充の文法問題の生成（prompt_version: 2026-07-30.1）

依頼 JSON の `material` を読み、**TOEIC Part 5 と同じ形**の空所補充問題を作る。出力は
`english/schema/generation-result.schema.json` に準拠した JSON 1ファイル。

市販の問題集から問題文を写さない。素材（VOA の記事・TED の字幕・TOEIC 語彙）に出てくる
語と場面を使って、こちらで作る。

## sentence

- 1文。空所は `____`（アンダースコア4つ）ちょうど1箇所。
- 素材に出てきた語・話題を使う。素材と無関係な一般例文で埋めない。
- ビジネス文脈（会議・注文・出張・人事）を優先する。TOEIC の出題場面がそこに偏るため。

## choices / answer_index

- 4択が基本（3–5択まで可）。`answer_index` は 0 始まり。
- **誤答選択肢は同じ語の別の形にする。** これが Part 5 の作り方で、
  「意味を知っているか」ではなく「形を選べるか」を問う形になる:
  - 品詞: `succeed` / `success` / `successful` / `successfully`
  - 態・時制: `has completed` / `was completed` / `completing` / `to complete`
  - 前置詞・接続詞: `despite` / `although` / `because of` / `however`
- ランダムな無関係語を混ぜない。1つでも混ざると消去法で解けてしまう。

## point

問われている文法項目を短く書く（`副詞と形容詞の区別` / `分詞構文` / `前置詞 vs 接続詞`）。
**誤答が同じ `point` に集中したとき、文法ノートのどこを書き足すべきかがこれで決まる**ので、
「文法」のような粗い書き方をしない。

## explanation

正解の理由に加えて、**各誤答がなぜ入らないか**を書く。誤答時にそのまま提示される。

## sub_skill

| 値 | どういう問題か |
|---|---|
| `knowledge` | 規則そのものを知っているかを問う |
| `recognition` | 正しい形を選べるか（Part 5 の標準） |
| `production` | 与えられた語を適切な形に変えて入れる |
| `processing_speed` | 平易だが即答が要る |

## 制約

- 空所は1つだけ。2箇所空けない。
- 正解が2つ成立する文にしない（曖昧なら文脈を足して1つに絞る）。
- 1回の生成は依頼 JSON の `count_per_kind` 件まで。
