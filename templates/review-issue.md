# 添削Issue テンプレート

ChatGPT が添削結果を Issue 化するときは、この形式で出力する。
これが Codex への仕様書になるため、**曖昧さを残さないこと**。

---

## Title

`[<review_id>] <一行で何を直すか>`

例: `[dsa.ch02.list] 環状リストの番兵の説明が実装と食い違っている`

## Body

```markdown
## 対象

| 項目 | 値 |
|---|---|
| Repository | yuta-u-tech/<repo> |
| Base Commit | <manifest の commit をそのまま貼る> |
| Review ID | <例: dsa.ch02.list> |
| Source File | <例: src/chapters/ch02.tex> |
| PDF Page | <manifest の page_start–page_end> |

## 問題

<現状の記述の何が問題か。「読みにくい」ではなく、
 事実として何が誤っている / 欠けているかを書く。>

<該当箇所を引用する:>

> 現状の記述をここに引用

## 修正仕様

<Codex が判断を挟まずに実装できる粒度で書く。>

1. <具体的に何をどう書き換えるか>
2. <複数箇所あれば列挙>

## 変更禁止事項

- 上記以外の箇所は触らない
- 既存の記号体系（<この章で使っている記号>）を変えない
- 情報量を減らさない（要約・削除をしない）
- 新しい環境・パッケージを追加しない

## 完了条件

- [ ] <修正が反映されている>
- [ ] `latexmk -lualatex src/main.tex` が通る
- [ ] REVIEW-ID ヘッダが残っている
- [ ] 上記「変更禁止事項」に反する差分がない
```

## ラベル

| ラベル | 意味 |
|---|---|
| `review` | 添削由来の Issue |
| `codex-ready` | 仕様が確定し、Codex が着手してよい |
| `needs-decision` | 方針が未確定。人間の判断待ち |

`codex-ready` が付くまで Codex は着手しない。
