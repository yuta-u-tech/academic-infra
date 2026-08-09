# TOEIC 解答提出の Google Forms 化（設計メモ）

## 背景

`academic_audio_cli.py`（Part2/3/4 リスニング）は `answers.json` を生成するだけで、
解答提出・採点・学習ループ（`~/.academic-english/english.db` の `attempt`/`skill_state`）への
反映が存在しない。Part5/Part7（`toeic_reading_cli.py`）・語彙（`toeic_vocab_cli.py`）は
PDF配布までで、採点はローカルUI（`acenglish serve`）を別途開いた場合のみ機能する。

紙PDFのままでは「解いた→採点→次回出題に反映」が閉じないため、Google Forms を解答提出窓口にし、
選択式は quiz mode の自動採点、記述式は自己採点（3択）を使って閉ループにする。

## 決定事項（Issue-002 相当）

**Google Sheets を正本データストアにはしない。** Forms が回答ごとに自動生成するリンク済み
スプレッドシートは「翌朝バッチが読み取って捨てる一時受け皿」として扱う。正本は既存の
`~/.academic-english/english.db`（`material`/`generated_item`/`attempt`/`skill_state`）のまま。

理由: 二重のデータストアを持つと同期漏れ・不整合の温床になる。Part5/Part7 が既に
`review_id` を主キーとした学習ループを持っており、それを壊さず「解答提出経路だけ」を
Forms に差し替えるのが最小変更。

- `problem_id`（仕様書の呼称）= 既存の `review_id` 命名規則をそのまま使う。
  例: リスニングなら `toeic.listening.part{2,3,4}.<set-id>.NNNN`
  （Part5が `toeic.part5.<set-id>.NNNN` を使っているのに合わせた形）。
- Form作成時、各設問の `review_id` ↔ Forms の質問項目ID の対応を `form_map.json` として
  Form作成の出力ディレクトリに保存する（翌朝バッチがスプレッドシートの行を `review_id` に
  逆引きするために必須）。
- アクセス制御（招待制）は新規に実装しない。Forms は Drive 上のファイルなので、
  既存の `_drive_common.py`（`https://www.googleapis.com/auth/drive` スコープを既に持つ）で
  `files.permissions.create` を呼んで共有範囲を絞る。Forms 専用の新規 OAuth クライアントは
  `forms.body`（作成・編集）と `forms.responses.readonly`（回答読み取り）の2スコープのみで足りる。
- 翌朝バッチが `attempt` テーブルへ書き込む際は、既存の `acenglish.study.answer()` が前提とする
  「ローカルUIのセッション」の外から呼ばれる。ここは `study.py` 側の拡張が必要
  （フォーム経由の回答をひとつの仮想セッションとして記録する関数を新設する）。
  **この部分は今回のフェーズでは未着手** — Issue-006 相当として別途実装する。

## フェーズ計画

1. **Phase 0（本メモ + フィージビリティ）**: 完了
2. **Phase 1（Forms自動作成モジュール）**: `scripts/authorize_forms.py` / `scripts/_forms_common.py` /
   `scripts/toeic_forms/`（選択式quiz・記述式自己採点の両方のForm組み立て）/
   `scripts/toeic_forms_cli.py create`
3. **Phase 2（TeX埋め込み）**: 既存 `toeic_reading/render.py` ・ `academic_audio` のワークシート生成に
   Form URL の `\href{}` 埋め込みを追加。**Form作成(Phase1)が終わってからでないと呼べない
   （URLがまだ無いため）** — 順序制約はここで自然に強制される。
4. **Phase 3（翌朝バッチ）**: スプレッドシート読み取り→`form_map.json`で`review_id`に逆引き→
   `study.py`にフォーム経由記録用の関数を追加→`attempt`/`skill_state`更新。
5. **Phase 4（間隔反復統合）**: 既存の `weak-points`（直近誤答の抽出）とスケジューリングロジックを統合。

Phase 1 のみ今回のセッションで実装する。Phase 2以降は Form URL が実際に手に入ってから
（＝ Phase 1 が実運用で1回動いてから）着手するのが安全なので、次回セッションに回す。
