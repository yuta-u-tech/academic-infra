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
- **許可アカウント（2026-08-09 決定）**: `--allowed-email` に渡す既定の許可リストは
  `1207sato.yuki@gmail.com` と `inutarouhiroto0222@gmail.com` の2件。
  既存の「Academic Materials」Driveフォルダ（`GDRIVE_PARENT_FOLDER_ID`）の共有先3件
  （上記2件 + `erika_129@iCloud.com`）のうち、本人確認の上でこの2件に絞ることが決まった
  （`erika_129@iCloud.com` は含めない）。Drive共有と完全に同一のリストではない点に注意
  （Formsは別の招待制リストとして個別管理する）。

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
5. **実運用での動作確認**: 完了（2026-08-09）。テスト用の1問Formで
   Form作成→回答→`record`→`english.db`反映まで通し、実APIでしか分からない不具合
   （itemIdの形式制約・responder_urlの誤った組み立て・itemIdとquestionIdが別物である点）
   を3件発見・修正。続けて実際の2026-08-09分のPart5セット（50問）で本番運用を実施
   （Form作成→PDF公開→回答回収→`record`まで完走、39/50正解）。
6. **`shuffle` コマンドの追加（2026-08-09、ユーザー指摘）**: 「通常30問＋苦手重点20問」を
   前半/後半のまま出題すると、出題順から復習問題だと分かってしまう。
   `toeic_reading_cli.py shuffle --items items.json` で設問順序を機械的にシャッフルする
   工程を追加し、ingest/Form作成/worksheet生成のいずれよりも前に必須実行する運用にした
   （`review_id`はシャッフル後の並び順で決まるため、shuffleが最初）。
7. **Part7のForms対応（2026-08-09）**: Part5と同じ流れを`SKILL.md`のPart7節にも追加。
   Part7はpassageに複数設問がぶら下がる構造なので、Form変換時は「本文＋設問文」を
   1問ごとに自己完結させる（Formsには本文を1回だけ表示する機能が無いため）。
8. **リスニング(Part2/3/4)の学習ループ接続（2026-08-09）**: リスニングはそもそも
   `english.db`への取り込み経路自体が無かった（Form連携以前からのギャップ）。
   `acenglish.items.ListeningItem`・`acenglish.sources.toeic_listening`・
   `acenglish.fetch.import_toeic_listening`/`import_toeic_listening_passage`・
   `academic_audio_cli.py listening ingest-db` を新設し、Part5/Part7と同じ形で
   Forms連携＋学習ループ反映を実装した。`study.record_form_response()`はkind非依存の
   設計だったため、record側の変更は不要だった。
9. **Phase 6（残作業・次回以降）**:
   - 記述式（自己採点）の記録は未実装（`answer()` の `correct` 外部指定への拡張が必要）。
   - 間隔反復スケジューラと既存の `weak-points`（直近誤答の抽出）ロジックの統合は未着手。
   - 翌朝バッチの自動化（cron等）はしていない。「答え終わった」等の発話をトリガーに
     `toeic_forms_cli.py record` を都度実行する運用（他のTOEIC教材と同じ制約）。
   - リスニングの実運用での動作確認（実際にFormを作って回答→`record`まで通す）はまだ
     行っていない（Part5は2026-08-09に実運用確認済み）。
