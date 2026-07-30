# 英語学習機能の統合設計（実装前分析）

> ステータス: **MVP 実装済み（2026-07-30）**。閉ループ（§9）は通っている。
> 方針は3点とも承認済み: §2 の案C（内蔵＋既存英語資産の再利用）／FastAPI + 素の HTML/JS ／
> 長期正本は GitHub（§7 の乖離を承認）。
> 未着手の範囲は §9「やらないこと」と §10 を参照。
> 最終更新: 2026-07-30

---

## 0. 調査で判明した最重要事項

**英語学習の資産は既に3つ存在し、うち2つは設計済み・未実装のまま止まっている。**
新規に設計を起こす前に、これらとの関係を決めないと確実に二重実装になる。

| リポジトリ | 状態 | 中身 |
|---|---|---|
| `goigoi` | 設計確定・実装前 | Expo(React Native) の SRS 単語アプリ。ADR 2本、`schema/word.schema.json` v1 確定済み |
| `goigoi-data` | 作成済み・空 | private。`words/<uuid>.json` を GitHub Contents API で同期する保存層 |
| `listening-materials` | 設計フェーズ | TED字幕 → cloze/シャドーイング/表現抽出。**配信は 127.0.0.1 のローカルWebアプリと決定済み** |

決定的なのは次の2点。

1. **`word.schema.json` の `source` enum は既に `["ted", "academic", "manual"]`**、`source_ref` の例は
   `"academic:logic"`。つまり **academic-infra から語彙を流し込む経路は既に設計に織り込まれている**
   （実装だけが無い）。今回の要求 §3「専門語彙の生成」はこのスキーマの空き枠にそのまま入る。
2. **`listening-materials/DESIGN.md` §5 が「127.0.0.1 のローカルWebアプリで即時採点」を既に決定済み。**
   今回の要求 §9 と同じもの。ここで別のWebアプリを立てると、同じ用途のローカルサーバが2本立つ。

→ 結論: 今回作るローカルWeb UIは **listening-materials の cloze 配信先を兼ねる「学習コックピット」** として
一本化する。goigoi は端末側（iPhone）のSRSクライアントとして残し、語彙の長期保存は
**goigoi-data を正本として再利用する**（新しい語彙ストアを作らない）。

---

## 1. Academic-Infra の現状分析

### 1.1 実体

academic-infra は**学習基盤ではなく、ビルド・配布基盤**である。学習状態を一切持たない。

```
GitHub(TeX, 正本) → GitHub Actions → dist/ → Google Drive(配布) → 閲覧者/GoodNotes
                         ↑                                              ↓
                    Codex/PR ← GitHub Issue ← Claude(pm-desk) ← Driveコメント
```

- 依存は `PyYAML` / `google-api-python-client` / `google-auth` / `pypdf` のみ。**DBなし・Webサーバーなし・Nodeなし。**
- CI は科目リポジトリごとに matrix 実行（`templates/document.yml`）。
- `~/academic-infra` 自体は **public**（README 明記）。秘密情報を置かない前提。

### 1.2 成果物と結合鍵

| 生成物 | 役割 |
|---|---|
| `latest.pdf` | 人間向け（GoodNotes へ自動ミラー） |
| `latest.md` | 全文 Markdown |
| `sections/chNN-MM.md` | **検索単位。front matter 付き。英語機能の入力はここ** |
| `review-manifest.json` | PDF ⇄ MD ⇄ TeX の対応表。`commit` を保持 |

**`REVIEW-ID` が全体の結合鍵**（`dsa.ch02.list` / セクションは `dsa.ch02.list.s01`）。
README に「変えない」と明記されている。
→ **英語機能の「学習対象の住所」も REVIEW-ID をそのまま使う。新しいID体系を作らない。**

### 1.3 既存の「資料を無断で上書きしない」フロー（要求 §5 は既に存在する）

要求 §5「Draft として保存し、確認後に反映」は、**既に実装されている**。新規に作る必要はない。

```
Drive コメント
  → fetch_drive_comments.py（未処理のみJSON出力）
  → Claude が評価し findings.json を書く（templates/review-issue.md 形式）
  → promote_drive_comments.py --pick 1,3 → gh issue create
  → .state/<course>/processed-comments.json に記録（再提示されない）
  → Codex が実装 → PR → merge → CI → Drive 更新
```

lecture-capture 側も同型（`lecture create-issue` が `review-findings.json` を読む）。

→ **英語学習で見つかった「ノートの説明不足」も、この findings.json → Issue 経路に合流させる。**
独自の Draft テーブル・独自の承認UIを新設するのは、既存フローの二重化になる。

### 1.4 状態管理の現状

- `.state/<course_id>/processed-comments.json` — 軽量 JSON。SQLite は無い。
- 資料の「状態」を持つのは lecture-capture 側の状態機械
  （`GENERATING_DRAFT` → `DRAFT_PUBLISHED` → `MERGED` → `PUBLISHED` → `AUDIO_DELETED`）。
- 学習ログの受け皿は gjp / life-repo（日記・活動ログ）と progress-ledger（プロジェクト進捗）。
  **理解度・誤答を入れる場所はどこにも無い** → ここが新設の必要な唯一のデータ層。

### 1.5 ローカルWeb UI の先例

`gjp web`（127.0.0.1:8765）は **Python 標準ライブラリの `http.server` のみ**で書かれている
（`pyproject.toml` の依存は matplotlib だけ）。`pm-agent dashboard` は Node(TypeScript)。
→ スタック選択の判断材料。§11 で扱う。

---

## 2. 統合方式の比較（要求 §13 の必須比較項目）

| | A: 独立 English-Infra | B: academic-infra へ内蔵 | **C: 内蔵 + 既存英語資産の再利用（推奨）** |
|---|---|---|---|
| 語彙の保存 | 新規に作る | 新規に作る | **goigoi-data を正本として再利用** |
| リスニング | 新規に作る | 新規に作る | **listening-materials を取り込む** |
| 資料参照 | 外部から `sections/*.md` を読む | 直接読む | 直接読む |
| ノート還元 | 別経路を作る必要 | 既存 findings.json 経路に合流 | 既存 findings.json 経路に合流 |
| academic-infra の public 制約 | 影響なし | **学習履歴を置けない**（要対策） | 同左（SQLite をリポジトリ外に置いて回避） |
| 端末（iPhone）での復習 | 作れない | 作れない | **goigoi(Expo) がそのまま使える** |
| 二重実装リスク | 高（3系統が並立） | 高 | **低** |

**推奨: C。**

理由は §0 の通り、goigoi のスキーマが既に `academic` ソースを想定しており、listening-materials が
既にローカルWebアプリを配信先と決めているため。A/B のどちらを取っても、この2つを捨てるか放置するかに
なり、「単語は goigoi、読解は新アプリ、リスニングは3つ目」という分裂した状態が残る。

要求 §13 の最終方針（「Academic-Infra の資料・ノート・演習・学習履歴を継続的に成長させる機能増強」）
とも C が最も整合する。

### 2.1 C の配置

```
~/academic-infra/                 ← 機能の実装先（public。コードのみ）
├── scripts/acinfra/              ← 既存: ビルド
├── scripts/acenglish/            ← 新規: 英語教材生成・学習者モデル・API
├── english/
│   ├── prompts/                  ← 生成プロンプト（Claude が担う判断の仕様書）
│   └── schema/                   ← 生成物の JSON Schema
└── web/                          ← 新規: ローカル学習コックピット UI

~/.academic-english/              ← 新規（リポジトリ外・0700）。運用状態
└── english.db                    ← SQLite。学習履歴・誤答・学習者モデル

~/goigoi-data/                    ← 既存: 語彙の長期正本（private）
<科目リポジトリ>/english/          ← 新規: 正式な英語教材（TeX/MD）。PR 経由でのみ更新
```

**`~/academic-infra` は public なので、学習履歴・誤答・語彙は絶対に置かない。**
これは既存 README の制約であり、要求 §10 の「SQLite を Drive 上で直接稼働させない」より強い制約。

---

## 3. 既存機能と新規機能の境界

| 領域 | 既存（触らない） | 新規 |
|---|---|---|
| TeX ビルド | `build_artifacts.py` / `acinfra/*` | — |
| Drive 同期 | `update_drive.py` | — |
| REVIEW-ID | `add_review_headers.py`, ID 体系 | 参照のみ（新IDを振らない） |
| Issue 昇華 | `promote_drive_comments.py`, `templates/review-issue.md` | **英語学習由来の findings.json を同形式で書く** |
| 学習状態 | なし | `~/.academic-english/english.db` |
| 教材生成 | なし | `acenglish/generate.py` + Claude 判断 |
| Web UI | なし（gjp web は別用途） | `web/` 学習コックピット |
| 語彙 | `goigoi` スキーマ v1 | goigoi-data への書き込み経路 |

**破壊してはいけない既存仕様（調査で確認済み）**

1. `REVIEW-ID` を変更・再採番しない。
2. `dist/` の成果物ファイル名（`latest.pdf` / `latest.md` / `sections/chNN-MM.md` / `review-manifest.json`）を変えない。
3. Drive 更新は main への merge 時のみ。学習アプリから Drive へ直接書かない。
4. `academic.yml` の必須キーを増やさない（既存7科目が全て壊れる）。英語設定は任意キーで追加する。
5. `~/academic-infra` に秘密情報・個人データを置かない（public）。
6. `word.schema.json` の `schema_version: 1` を破らない（`additionalProperties: false` のため、
   フィールド追加は v2 への昇格が必要）。
7. `.state/<course>/processed-comments.json` の形式を変えない。

---

## 4. データフロー

```
[生成]
科目リポジトリ dist/sections/chNN-MM.md  (+ review-manifest.json の commit/review_id)
   → acenglish generate --review-id dsa.ch02.list.s01 --kind vocab|reading|cloze
   → Claude が判断して生成物 JSON を書く（決定論コードでは書かない。既存の思想に合わせる）
   → 一時生成物: SQLite の generated_item テーブル（検証前）
   → 検証済み・再利用するもの: 語彙 → goigoi-data / 教材 → 科目リポジトリ english/（PR経由）

[学習]
ローカル Web UI (127.0.0.1)
   → 出題（SQLite の復習キュー順）
   → 回答（正誤 + 所要時間 + 自信度 + ヒント使用 + 再回答回数）
   → SQLite: attempt に記録

[評価・還元]
attempt → 誤答原因の分類（Claude）
   → 学習者モデル更新（SQLite: skill_state）
   → 復習キュー再計算（SM-2。goigoi と同一アルゴリズム）
   → 「教材不足」と判定されたもの → findings.json を書き出す
   → 既存 promote_drive_comments.py 相当の経路で GitHub Issue 化（ユーザー確認後）
```

**Drive はこのフローに一切登場しない。** 学習アプリは Drive を読み書きしない
（既存設計「Drive は配布層、履歴は git」を維持）。

---

## 5. ノート・教材更新フロー（要求 §5 / §8）

要求の「Draft」は、既存の3段階にマップする。**新しい承認UIを作らない。**

| 要求の概念 | 実体 |
|---|---|
| 修正候補 / 追記候補 | SQLite `revision_candidate`（未確定。Claude が生成、ユーザー未確認） |
| Draft | `findings.json`（`templates/review-issue.md` 形式。ユーザーが `--pick` で選ぶ） |
| 正式反映 | GitHub Issue → Codex → PR → merge → CI → Drive |

誤答から資料更新までの流れ:

```
同一 review_id で誤答が反復
  → Claude が原因を分類:
      knowledge_gap        本人の理解不足    → 復習問題を追加生成（資料は触らない）
      material_gap         資料の説明不足    → revision_candidate 生成 → findings.json → Issue
      production_gap       認識はできるが産出できない → 産出型演習を追加生成
      vocabulary_gap       語彙不足          → goigoi-data へ語彙投入
      parsing_gap          構文解析不足      → 構文分解演習を生成
      speed_gap            処理速度不足      → 時間制限付き再出題
  → material_gap のみが資料更新へ進む。それ以外は演習生成に留める
```

この分岐が要求 §8 の「教材不足か本人の理解不足かを判定」の実装形。

---

## 6. 資料の状態（要求 §4）

**新しい状態名を導入せず、既存の3つの情報源の合成で表す。**

| 要求の状態 | 既存での表現 |
|---|---|
| raw / processed | lecture-capture 状態機械（`GENERATING_DRAFT` 等） |
| reviewed / verified | GitHub PR のマージ状態 + `PUBLISHED` |
| learning | SQLite `skill_state` に該当 review_id の記録があるか |
| needs_revision | その review_id に open な `review` ラベル Issue があるか |
| expanded | 科目リポジトリ `english/` に生成物が存在するか |
| archived | git 履歴（既存: 「履歴は git が持つ」） |

**履歴の追跡は git が担う**（既存設計）。SQLite に資料の版管理を持たせない。
SQLite が持つのは「学習の観点から見た資料の状態」だけ。

---

## 7. SQLite と長期保存の責務分担

要求 §10 は2層（SQLite / Drive）だが、**この基盤では3層が正しい**。既存設計を優先する。

| 層 | 場所 | 持つもの |
|---|---|---|
| 運用状態 | `~/.academic-english/english.db`（0700, リポジトリ外） | セッション・回答・誤答・所要時間・自信度・習熟度・復習キュー・未検証の生成物・revision_candidate・ジョブ |
| **長期正本** | **GitHub**（科目リポジトリ `english/` + goigoi-data） | 正式な英語教材・語彙・ノート追記。全て PR / commit 経由 |
| 配布 | Google Drive | 既存通り `latest.*` / `sections/` のみ |

**要求 §10 との明示的な乖離**: 要求は「長期学習資産を Drive 同期フォルダへ保存」としているが、
academic-infra は「**GitHub を唯一の正本、Drive には最新の成果物だけ、履歴は git**」を明文化している
（README 冒頭）。Drive を保存層にすると、この基盤の中心的な設計判断を反転させることになる。
要求 §11 の「既存設計を優先」および §15「既存の設計思想を尊重」に従い、**長期保存は GitHub とする**。

SQLite のバックアップは `sqlite3 .backup` でスナップショットを取り、
goigoi-data と同じ private リポジトリ側に置く（Drive 上で直接稼働させないという要求は満たす）。

---

## 8. 学習者モデル案

要求 §7 の6ドメイン×サブスキルをそのまま採用する。表現は「正答率」ではなく多次元にする。

```sql
skill_state(
  domain,          -- vocabulary | grammar | reading | listening | writing | speaking
  sub_skill,       -- recognition | recall | usage | collocation | countability | ...
  target_ref,      -- review_id（例 dsa.ch02.list.s01）または語彙ID。教材横断は NULL
  mastery,         -- 0.0–1.0（推定習熟度）
  confidence,      -- 推定の確からしさ（試行数に依存）
  latency_ms_p50,  -- 処理速度
  hint_rate,       -- ヒント依存度
  retention_days,  -- 時間経過後の保持
  error_streak,    -- 同一誤りの反復回数
  updated_at
)
```

更新の根拠（要求 §7 の10項目）は `attempt` テーブルに全て残す:
`correct` / `elapsed_ms` / `self_confidence` / `hint_used` / `retry_count` / `error_cause` /
`edit_distance`（英作文の修正量） / `hesitation_marks`（発話の詰まり） / `days_since_last`。

**mastery は単純な正答率にしない**: 正答 × 短い所要時間 × ヒント無し × 高自信 のときだけ大きく上げ、
「正答したが遅い・ヒント有り・自信低い」は上げ幅を絞る（要求 §15 の最終項目に対応）。

SRS の間隔計算は **goigoi と同じ SM-2** を使う（`interval` / `ease_factor` / `repetitions`）。
別アルゴリズムを入れると goigoi-data の同期時に状態が壊れる。

---

## 9. MVP の範囲（要求 §14 の閉ループ一本）

**やること（この一本だけを通す）**

1. `acenglish select` — `courses.yml` + `review-manifest.json` から学習対象 section を選ぶ
2. `acenglish generate --kind vocab,reading` — `sections/chNN-MM.md` から語彙・読解問題を生成
   （生成の判断は Claude。決定論コードは入出力の器だけ）
3. ローカル Web UI（127.0.0.1）で出題・回答
4. `attempt` に 正誤/所要時間/自信度/ヒント/再回答 を記録
5. 誤答原因を §5 の6分類で保存
6. `skill_state` を更新
7. 復習キュー生成（SM-2）
8. `material_gap` の誤答から `revision_candidate` → `findings.json` を書き出す
9. `findings.json` を既存の Issue 昇華経路へ渡す（**ここは既存スクリプトを再利用**）

**やらないこと（MVP 外）**

- リスニング / スピーキング / 発音（音声I/O が別の重い問題）
- 英作文の添削（評価器の設計が別途必要）
- TOEIC 特化・論文読解特化のモード
- goigoi(Expo) 本体の実装（goigoi-data への**書き込み**だけ実装し、読む側は後）
- listening-materials の統合（設計上の接続点だけ用意し、実装は後）
- 認証・マルチユーザー（要求通り不要）

---

## 10. 将来的な拡張方針

1. listening-materials の `cloze.json` を同じ Web UI のタブとして取り込む（配信先の一本化）。
2. goigoi(Expo) を実装し、goigoi-data 経由で PC ⇄ iPhone の双方向同期を通す。
3. 英作文添削 → `edit_distance` を学習者モデルへ。
4. スピーキング（録音は lecture-capture の ASR 基盤を再利用できる）。
5. 学習ログの gjp/life-repo への日次サマリ書き出し（pm-desk の夜の締めに合流）。

---

## 11. 想定されるリスク

| リスク | 内容 | 対策 |
|---|---|---|
| **public リポジトリへの個人データ流出** | academic-infra は public。学習履歴・誤答・語彙をうっかり置くと公開される | SQLite を `~/.academic-english/`（リポジトリ外・0700）に固定。`.gitignore` だけに頼らない |
| **スタックの分裂** | Next.js を入れると academic-infra に Node ツールチェインが増え、Python matrix CI と二重になる | §12 で要判断（下記の確認事項） |
| goigoi スキーマの破壊 | `additionalProperties: false` のため独自フィールドを足すと即バリデーション失敗 | v1 は触らない。追加情報は SQLite 側に持つ |
| 生成物の氾濫 | 一時生成問題が SQLite に溜まり続ける | `is_ephemeral` / `verified_at` を必須にし、未検証の一時生成物は N 日で掃除 |
| 資料の無断上書き | 要求 §15 の最重要制約 | 学習アプリは科目リポジトリへ**書き込まない**。findings.json を書くだけ |
| Drive 認証の失効 | OAuth 同意画面がテスト状態だとトークンが7日で失効（README 記載の既知問題） | MVP は Drive に触らないので影響しない |
| 生成品質のばらつき | 語彙・問題の選定は Claude 判断のため揺れる | 生成物に `generated_by` / `prompt_version` / `source_commit` を必須で持たせ、後から再現・比較できるようにする |
| SQLite の破損・消失 | 学習履歴は再生成できない | `sqlite3 .backup` を private リポジトリへ定期コミット |

---

## 12. 実装タスク分解

MVP を9タスクに分ける。上から順に依存している。

| # | タスク | 成果物 | 状態 |
|---|---|---|---|
| 1 | データモデル定義 | `english/schema/generation-result.schema.json` + SQLite DDL | 済 |
| 2 | DB 層 | `acenglish/db.py`（マイグレーション・0700・backup） | 済 |
| 3 | 学習対象の解決 | `acenglish/target.py`（aliases + manifest → section本文） | 済 |
| 4 | 生成の器 | `acenglish/generate.py` + `english/prompts/{vocab,reading}.md` | 済 |
| 5 | 学習者モデル | `acenglish/model.py`（mastery更新 + SM-2） | 済 |
| 6 | 誤答分類 | `acenglish/diagnose.py`（6分類 + material_gap昇格） | 済 |
| 7 | ローカル API | `acenglish/api.py`（非ループバックを拒否） | 済 |
| 8 | Web UI | `web/index.html`（出題・自信度・ヒント・診断表示） | 済 |
| 9 | 還元経路 | `acenglish/promote.py` → 既存 `promote_drive_comments.py` | 済 |
| 10 | pm-desk 統合 | `SKILL.md` 「### 11. 英語学習」 | 済 |

テストは `tests/test_english_*.py`（76件）。特に固定してあるのは以下で、いずれも
設計上ここが崩れると要件を満たさなくなる点:

- 「正答だが遅い/ヒント有り/自信低い」の上げ幅が「正答で速い」より小さいこと
- 誤答1回では資料のせいにせず、`knowledge_gap` の3連続でのみ `material_gap` へ昇格すること
- 語彙不足・速度不足の反復は資料修正へ回さないこと
- 出題 API が答え（`answer_index` / `word` / `explanation`）を返さないこと
- 非ループバックへのバインドを拒否すること
- 出力した `findings.json` を既存 `promote_drive_comments.py` がそのまま Issue 本文にできること

### 未着手（MVP 外・§9 の「やらないこと」と対応）

- リスニング / スピーキング / 発音、英作文添削
- goigoi-data への語彙書き出し（スキーマは合わせてあるが経路は未実装）
- listening-materials の cloze をこの UI へ取り込む
- SQLite バックアップの定期実行（`acenglish_cli.py backup` はあるが自動化していない）

---

## 13. 着手前に確認が必要な事項

1. **統合方式**: §2 の C（内蔵 + goigoi/listening-materials 再利用）でよいか。
2. **技術スタック**: 要求 §11 は Next.js + FastAPI。既存 academic-infra は Python のみ（Node 無し）、
   gjp web は標準ライブラリのみ。要求 §11 自身が「既存構成と衝突する場合は既存設計を優先」と
   しているため、判断が必要。
3. **長期保存層**: §7 の乖離（Drive ではなく GitHub を正本とする）を承認いただけるか。
