# TOEIC 解答提出の Google Forms 化（設計メモ）

## 背景

`academic_audio_cli.py`（Part2/3/4 リスニング）は `answers.json` を生成するだけで、
解答提出・採点・学習ループ（`~/.academic-english/english.db` の `attempt`/`skill_state`）への
反映が存在しない。Part5/Part7（`toeic_reading_cli.py`）・語彙（`toeic_vocab_cli.py`）は
PDF配布までで、採点はローカルUI（`acenglish serve`）を別途開いた場合のみ機能する。

紙PDFのままでは「解いた→採点→次回出題に反映」が閉じないため、Google Forms を解答提出窓口にし、
選択式は quiz mode の自動採点、記述式は自己採点（3択）を使って閉ループにする。

## 決定事項（Issue-002 相当）

**Google Sheets を正本データストアにはしない。** 正本は既存の
`~/.academic-english/english.db`（`material`/`generated_item`/`attempt`/`skill_state`）のまま。

（2026-08-09 実装時の変更: 当初は「Formsのリンク済みスプレッドシートを翌朝バッチが読む」
想定だったが、Forms API自体に `forms.responses().list()` があり、
`forms.responses.readonly` スコープだけで回答を直接取れることが分かったため、
Sheets API・リンク済みスプレッドシートの解決は使わないことにした。スコープが一つ減り、
実装も単純になる。）

理由: 二重のデータストアを持つと同期漏れ・不整合の温床になる。Part5/Part7 が既に
`review_id` を主キーとした学習ループを持っており、それを壊さず「解答提出経路だけ」を
Forms に差し替えるのが最小変更。

- `problem_id`（仕様書の呼称）= 既存の `review_id` 命名規則をそのまま使う。
  例: リスニングなら `toeic.listening.part{2,3,4}.<set-id>.NNNN`
  （Part5が `toeic.part5.<set-id>.NNNN` を使っているのに合わせた形）。
- Form作成時、各設問の `review_id` ↔ Forms の質問項目ID（+ 選択式なら choices）の対応を
  `form_map.json` としてForm作成の出力ディレクトリに保存する（翌朝バッチが
  `forms.responses().list()` の回答を `review_id` に逆引きするために必須）。
- アクセス制御（招待制）は新規に実装しない。Forms は Drive 上のファイルなので、
  既存の `_drive_common.py`（`https://www.googleapis.com/auth/drive` スコープを既に持つ）で
  `files.permissions.create` を呼んで共有範囲を絞る。Forms 専用の新規 OAuth クライアントは
  `forms.body`（作成・編集）と `forms.responses.readonly`（回答読み取り）の2スコープのみで足りる。
- `study.py` に `find_item_id_by_review_id()` / `record_form_response()` を追加した。
  既存の `answer()` の閉ループ（採点・誤答分類・復習スケジューリング）はそのまま通し、
  `item_id` の代わりに `review_id` から呼べるようにしただけ。**選択式のみ対応。**
  記述式（自己採点）は `item.check()` が比較できる「正解」を持たない
  （本人の自己申告そのものが正誤）ため、`answer()` の
  `correct = item.check(response)` という前提に乗らず、未実装のまま残した。
  対応するには `answer()` に `correct` の外部指定を許す経路を足す必要がある。

## フェーズ計画

1. **Phase 0（本メモ + フィージビリティ）**: 完了
2. **Phase 1（Forms自動作成モジュール）**: 完了。`scripts/authorize_forms.py` /
   `scripts/_forms_common.py` / `scripts/toeic_forms/`（選択式quiz・記述式自己採点の両方の
   Form組み立て）/ `scripts/toeic_forms_cli.py create`
3. **Phase 2（TeX埋め込み）**: 完了。`toeic_reading/render.py` ・ `academic_audio/worksheet.py` の
   ワークシート生成に Form URL の `\href{}` 埋め込みを追加
   （`academic_audio_cli.py listening attach-form-url` / `toeic_reading_cli.py worksheet --form-url`）。
4. **Phase 3（翌朝バッチ・選択式のみ）**: 完了。`scripts/toeic_forms_cli.py record` が
   `forms.responses().list()` を読み、`form_map.json` で `review_id` に逆引きし、
   `study.record_form_response()` で `attempt`/`skill_state` を更新する。
5. **Phase 4（残作業・次回以降）**:
   - 記述式（自己採点）の記録は未実装（上記の `answer()` 拡張が必要）。
   - 間隔反復スケジューラと既存の `weak-points`（直近誤答の抽出）ロジックの統合は未着手。
   - `authorize_forms.py` によるOAuth同意（本人のブラウザ操作が必須）・
     知人の許可Googleアカウント一覧の決定は、コードでは代行できない残作業。
   - 実運用での動作確認（実際に1件Formを作って回答→`record`まで通す）はまだ行っていない。
