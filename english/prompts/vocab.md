# 専門語彙カードの生成（prompt_version: 2026-07-30.1）

`acenglish_cli.py request` が出す依頼 JSON の `material`（= `sections/*.md` の本文）を読み、
**その分野を英語で扱うために要る語彙**をカード化する。出力は
`english/schema/generation-result.schema.json` に準拠した JSON 1ファイル。

## 何を選ぶか

資料に日本語で書かれている概念のうち、**英語の文献・講義・議論で必ず出てくる語**を選ぶ。

- 選ぶ: `binary search tree`, `in-order traversal`, `amortized cost`, `sentinel node`
- 選ばない: 一般語（`important`, `problem`）、その分野に固有でない語、資料に出てこない概念

日本語資料に対応する英語表現が資料内に無い場合は、**標準的な学術英語の対訳を補う**
（これが「日本語理解と英語運用を並行して発展させる」の実体）。

## 各フィールド

| フィールド | 書き方 |
|---|---|
| `word` | 見出し語。複合語・熟語もそのまま1カードでよい |
| `meaning` | 日本語。資料中の説明と食い違わせない |
| `example` | **資料の内容に即した英文**を書く。汎用例文で埋めない。無ければ null |
| `part_of_speech` | `noun` / `verb` / `adjective` 等 |
| `collocations` | その語が実際に取る組み合わせ（`traverse a tree`, `balance factor`）。無ければ空配列 |
| `sub_skill` | 何を訓練するカードか。`recognition`（見て分かる）/ `recall`（思い出して書ける）/ `usage` / `collocation` / `countability` |
| `difficulty` | 1–5。学部で初出なら2、分野特有で紛らわしければ4以上 |
| `reason` | **なぜこの語を選んだか**。「資料の中心概念で英語論文に頻出」など、後から取捨できる根拠 |

`sub_skill` の既定は `recall`。同じ語を `recognition` と `recall` の2枚に分けてもよい
（分けた場合、学習者モデルは「見れば分かるが書けない」を検出できるようになる）。

## 制約

- `word` を `meaning` の中に混ぜて書かない（出題時に答えが見えてしまう）。
- 資料に無い主張を `meaning` に足さない。曖昧なら `reason` にその旨を書いて難易度を上げる。
- 1回の生成は依頼 JSON の `count_per_kind` 件まで。足りない分を水増ししない。
