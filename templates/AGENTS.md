# AGENTS.md — 資料修正エージェント向け編集ポリシー

このファイルは Codex / Claude 等が本リポジトリの TeX を修正するときに従う規約である。
**このファイルは必ず git 管理下に置くこと**（`.gitignore` に入れると Codex から見えない）。

## 役割

東京理科大学 工学部 情報工学科の学生が書いた講義まとめノートを保守する。
新しく書くのではなく、**既にある記述を直す**のが仕事である。

## 絶対規則

1. **情報量を減らさない。**
   要約・圧縮・「簡潔にする」目的での削除は禁止。冗長に見えても残す。
   削除してよいのは、Issue が明示的に削除を指示した箇所だけ。

2. **勝手に内容を追加しない。**
   Issue に書かれていない解説・例・脚注・章を足さない。
   「あったほうが親切」は理由にならない。

3. **指定箇所以外を書き換えない。**
   Issue の Review ID / Source File が指す範囲だけを触る。
   ついでの整形・リネーム・パッケージ追加は別 Issue にする。

4. **記号体系を維持する。**
   既存の記号・変数名・環境の使い分けを変えない。
   `$n$` を `$N$` にする類の「統一」は、Issue で指示された場合のみ。

5. **局所修正を優先する。**
   同じ結果が得られるなら、差分が小さい方を選ぶ。
   構造変更は Issue が明示的に求めたときだけ。

## LaTeX 規約

- 環境ブロック内は **スペース2つ** でインデントする。
- パッケージ追加は `src/includes/protocol.tex` に書く。
- マクロ・レイアウトは `src/includes/preamble.tex` に書く。
- 章ファイルは `src/chapters/chNN.tex`。`\subfile` で main から読む。
- 定義・定理・証明などは `protocol.tex` 既定の tcolorbox 環境を使う
  （`definition` / `theorem` / `tproof` / `example` / `remark` / `exercise` など）。
  **新しい環境を勝手に定義しない。**
- 数式の末尾にピリオドを付けない。
- 微分は `physics` パッケージの `\dv` / `\pdv` を使う。

## REVIEW-ID ヘッダ

各章ファイルの冒頭には次の形式のヘッダがある。**消さないこと。**

```tex
% REVIEW-ID: dsa.ch02.list
% REVIEW-TITLE: リスト
% REVIEW-KEYWORDS:
%   線形リスト
%   環状リスト
```

内容を大きく変えたときは `REVIEW-KEYWORDS` を追随させる。`REVIEW-ID` は変えない
（Issue・manifest・Drive 上の Markdown から参照されているため）。

## ビルド確認

修正後、必ずビルドが通ることを確認する。

```bash
latexmk -lualatex -interaction=nonstopmode -halt-on-error src/main.tex
```

**通らない状態で PR を出さない。**

## Pull Request

PR 本文に次を書く。

- 対応する Issue 番号
- 触った Review ID と Source File
- 何を、なぜ変えたか（1行ずつ）
- ビルドが通ったことの確認
- **意図的に変えなかったこと**（Issue で言及されたが対応しなかった点があれば）

## 迷ったとき

Issue の指示が曖昧なら、**推測して実装せず PR にコメントで質問する**。
情報量を減らす方向の判断は、常に間違いだと考えてよい。
