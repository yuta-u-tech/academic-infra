# 2026-07-24 夜: 実スキャンPDFでの本番検証計画

## 題材

`~/.lecture-capture/scan-src/参考書/数理統計学の考え方-20260724/`
(プリンタで実際にスキャンした新規資料、`page_001.jpeg`〜`page_074.jpeg` の74ページ)

Statistics科目は `~/.lecture-capture/config/lecture.yml` で現在
`force_high_ocr: true`（2026-07-23、メモリ不足でローカルVisionモデル運用を
保留し高精度Codexモデル `lecture_high` に戻した設定）になっている。
つまり現行フローはこの74ページ全てを画像のまま `lecture_high` に送っている。

## 目的

`scan-ocr-lab` / `scan-note-pipeline` で作ってきたパイプライン
（早期停止対策・ページ跨ぎ検証結合・self-consistencyによるブロック信頼度・
ルールベース分類・エスカレーション判定）が、合成劣化データではなく
**実際にスキャンした新規資料**で最初から最後まで通しで動くかを確認する。

あわせて、現行フロー（全ページ `lecture_high` 送信）と新フロー（ローカルOCR＋
エスカレーション対象ブロックのみ送信）の**実測トークン数（input/output両方）**を
比較し、プロジェクトの成功基準（「結局サブスクで動かすcodexのトークンを
少しでも減らせればこのプロジェクトは成功」）に対する具体的な数字を出す。

## 決定事項（2026-07-24 更新）

- **対象ページ**: 章の頭（1〜2章）は文章primaryで数式が少なく精度比較に
  向かないため、**本の途中からランダムに連続20ページ**を選ぶ方針に変更。
  `seed=20260724`で選定 → **30〜49ページ目**（`page_030.jpeg`〜`page_049.jpeg`）。
  `process_document.py --start-page 30 --limit 20` で指定する
  （`_discover_images`に`start_page`引数を追加済み）。
- **プロファイル**: 現在の実運用（Statistics = `force_high_ocr: true`）に
  合わせ、baseline・new_flowとも **`lecture_high`** で統一する
  （精度面で同格の比較にもなる）。
- **input/outputトークンの定義**: OCR〜ノート生成までの流れ全体の合計
  （`measure_codex_usage.py`が baseline・new_flow それぞれで input_tokens/
  output_tokensを積算する設計と一致）。
- **パッチ適用〜ノート生成まで実施する**: トークン計測だけで終わらせず、
  実際にCodexから返ってきたパッチを適用して最終的なノート（TeX）を組み立てる
  ところまでやる。ただし生成されたノートの客観的なレビューには別のエージェントが
  必要（このセッション内の実装スコープとは別に用意する）。

## 流れ

### 1. scan-ocr-lab: 30〜49ページ目(20ページ)を順にOCR

```bash
cd ~/scan-ocr-lab && source .venv/bin/activate
python3 scripts/process_document.py \
  --images-dir ~/.lecture-capture/scan-src/参考書/数理統計学の考え方-20260724 \
  --start-page 30 --limit 20 \
  --self-consistency-samples 2 \
  --out data/eval_reports/statistics_20260724_ocr.json
```

- 早期停止対策（再帰分割）・ページ跨ぎの冒頭検証＆結合（`recover_missing_page_start`）は
  常に有効。
- self-consistencyは `_page_needs_verification` の足切り（math_density・
  looks_complete・分割要否）を通過したページだけに実行される
  （`--self-consistency-always` は付けない＝本番相当の挙動を見る）。
- 範囲の先頭（30ページ目）は本全体の途中から始まるため、その前のページ
  （29ページ目）との文の連続性は検証できない（先頭ページは単独ページとして
  扱われる。これは仕様であり不具合ではない）。

### 2. scan-note-pipeline: ブロック化〜エスカレーション判定

```bash
cd ~/scan-note-pipeline
python3 scripts/process_document.py \
  --ocr-json ~/scan-ocr-lab/data/eval_reports/statistics_20260724_ocr.json \
  --out data/statistics_20260724_blocks.json
```

- `split_document_into_blocks`（ページ跨ぎ結合、`confidences_by_page`込み）→
  `classify_blocks` → `decide_escalations` → `build_upper_model_requests`。
- ここまではCodexを一切呼ばない。近似トークン削減率（文字数/4）が出る。

### 3. measure_codex_usage.py: 実測トークン比較

```bash
python3 scripts/measure_codex_usage.py \
  --images-dir ~/.lecture-capture/scan-src/参考書/数理統計学の考え方-20260724 \
  --requests-json data/statistics_20260724_blocks.json \
  --profile lecture_high \
  --out data/statistics_20260724_token_usage.json
```

- baseline: 20ページの画像をバッチ（5枚/呼び出し）でそのまま `lecture_high` へ。
- new_flow: エスカレーション対象リクエストのみを同じバッチ方式で送信。
- 最後にinput+output合計の削減率を出す。
- `--images-dir`のbaseline側は`--start-page`/`--limit`で30〜49ページ目に絞れる
  （`0efb277`, `bb42859`で.jpeg対応と合わせて実装済み。テスト8件パス確認済み）。
  例: `--start-page 30 --limit 20`。

**コスト注意**: 20ページ ÷ 5 = 4回のcodex exec呼び出し(baseline)+ new_flowのバッチ分。
1回あたり固定オーバーヘッドだけでも約1.3万トークンかかる。まず数ページで試してから
20ページ全体に広げる。

### 4. パッチ適用〜ノート生成

`apply_upper_model_patches` でCodexからの返答を反映し、`generate_tex_document` で
最終的なTeXを組み立てる。生成後のノートは客観的なレビューが必要
（別エージェントで実施予定、今回のスコープ外）。

## 前回との違い（メモ）

前回Statisticsでローカルモデル運用を試して失敗したのは、他アプリ
（Chrome/VS Code等）でタブを開きすぎてメモリを圧迫していたことが原因。
今回は他の重いアプリを閉じてから実行する。
