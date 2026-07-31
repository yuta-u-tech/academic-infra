# academic-infra

大学の各科目の TeX 資料を、**GitHub を唯一の正本**として管理し、
**Google Drive を AI ナレッジベース**として配布するための共通基盤。

科目リポジトリ側には設定をほとんど置かない。仕組みはすべてここにある。

## 何をするか

```
GitHub (TeX)  →  ChatGPT が添削  →  Issue  →  Codex 修正  →  PR  →  merge
                                                                      ↓
                                                            GitHub Actions
                                                                      ↓
                        latest.pdf / latest.md / sections/*.md / review-manifest.json
                                                                      ↓
                                                            Google Drive (Viewer 共有)
                                                                      ↓
                                          閲覧者の ChatGPT (Google Drive コネクタ)
```

GitHub Collaborator を配らずに資料を共有するのが目的。
Drive には**最新の成果物だけ**を置く。履歴は git が持つ。

## 成果物

| ファイル | 用途 |
|---|---|
| `latest.pdf` | 人間向け閲覧 |
| `latest.md` | 文書全体の Markdown |
| `sections/chNN-MM.md` | 検索単位に分割した Markdown（front matter 付き） |
| `review-manifest.json` | PDF ページ ⇄ Markdown ⇄ TeX の相互対応表 |
| `build.log` | LaTeX ログ |

PDF だけで運用しないのは、AI が検索・引用・要約しやすい形が別に必要なため。

## 新しい科目を追加する

1. `courses.yml` にエントリを追加する
2. 科目リポジトリのルートに `templates/academic.yml` をコピーして値を書き換える
3. `templates/AGENTS.md` をコピーする（**`.gitignore` に入れないこと**。Codex から見えなくなる）
4. `templates/document.yml` を `.github/workflows/document.yml` にコピーする
5. `dist/` を `.gitignore` に追加する
6. REVIEW-ID ヘッダを入れる:

   ```bash
   python3 scripts/add_review_headers.py --repo-root ../<repo> --dry-run   # 確認
   python3 scripts/add_review_headers.py --repo-root ../<repo>             # 適用
   ```

   章スラグを付けたい場合は、科目リポジトリのルートに `review-slugs.yml` を置く。

## ローカルで動かす

```bash
python3 -m pip install -r requirements.txt
python3 scripts/build_artifacts.py --repo-root ../<repo>
```

必要なもの: LuaLaTeX（TeX Live）, latexmk, pandoc, Python 3.11+。

> **注意**: `~/.latexmkrc` で `$aux_dir` / `$out_dir` を設定していても、
> `build_artifacts.py` は `-outdir` と `-auxdir` の両方を明示的に固定するため影響を受けない。
> 手で `latexmk` を叩くとログの出先が変わる点に注意。

## REVIEW-ID

各章ファイルの冒頭に置くメタデータ。「自然演繹のところを添削して」から
対象ファイルを一意に決めるための鍵。

```tex
% REVIEW-ID: dsa.ch02.list
% REVIEW-TITLE: リスト構造
% REVIEW-KEYWORDS:
%   線形リスト
%   環状リスト
```

`REVIEW-ID` は Issue・manifest・Drive 上の Markdown から参照されるため、**変えない**。

## 設計上の決定

**TeX は章単位のまま**（`src/chapters/chNN.tex`）。意味単位への分割は
**出力側**（`sections/*.md`）で行う。ソースを壊さずに検索粒度を得るため。

**セクションのファイル名は連番**（`ch02-05.md`）。日本語見出しからスラグを作ると
不安定で、見出しを直すたびにファイル名が変わってリンクが切れる。
人間向けの題名は front matter に持たせる。

**Drive 更新は main への merge 時のみ**。PR ごとに同期すると、未マージの内容が
閲覧者のナレッジベースに混ざる。

**このリポジトリは public**。private にすると科目リポジトリからの checkout に
PAT が必要になる。ここに秘密情報は置かない。

## Google Drive 認証

**サービスアカウントは使わない。** サービスアカウントは消費者 Gmail の Drive に
自前のストレージ квоタを持たず、共有フォルダにアップロードすると
`storageQuotaExceeded` で失敗する。代わりに **OAuth リフレッシュトークンで
「所有ユーザー本人として」書き込む**。ファイルはそのアカウントの 15GB に載る。

### セットアップ（初回のみ）

1. 資料配布用の Gmail を用意する（個人メールと分けると管理が楽）。
2. [Google Cloud Console](https://console.cloud.google.com/) でその Gmail にログインし、
   プロジェクトを作成 → **Google Drive API** を有効化。
3. OAuth 同意画面を **External** で作成し、テストユーザーにその Gmail を追加。
4. 認証情報 → **OAuth クライアント ID**（アプリの種類: **デスクトップ**）を作成し、
   JSON をダウンロード。
5. リフレッシュトークンを取得する（ローカルでブラウザが開く）:

   ```bash
   python3 -m pip install -r requirements.txt
   python3 scripts/authorize_drive.py --client-secret ~/Downloads/client_secret_XXX.json
   ```

   表示された3つの値を控える。
6. Drive にフォルダ `Academic Materials` を作り、その ID（URL 末尾）を控える。
   閲覧者へはこのフォルダを **閲覧者（Viewer）** で共有する。
7. 科目リポジトリに Secret を4つ登録する:

   ```bash
   gh secret set GDRIVE_OAUTH_CLIENT_ID     --repo <owner>/<repo>
   gh secret set GDRIVE_OAUTH_CLIENT_SECRET --repo <owner>/<repo>
   gh secret set GDRIVE_OAUTH_REFRESH_TOKEN --repo <owner>/<repo>
   gh secret set GDRIVE_PARENT_FOLDER_ID    --repo <owner>/<repo>
   ```

Secret 未設定なら Drive 同期はスキップされ、成果物は Actions の Artifact から取れる。

> **注意**: リフレッシュトークンはパスワード同然。OAuth 同意画面が「テスト」状態の間、
> トークンは 7 日で失効することがある。継続運用するなら同意画面を「本番」に公開する
> （個人利用なので審査は不要）。将来的には OIDC + Workload Identity Federation も検討。

## 閲覧者コメント → GitHub Issue 昇華

Drive の `latest.pdf` は閲覧者にコメントを許可しているため、指摘は Drive のコメント機能に
溜まっていく。これを pm-desk（Claude）が読み、Issue化すべきものを判断して GitHub Issue に
昇華する。要約・判断は決定論コードでは書かず、Claude が担う。

```bash
# 1. 未処理（既にIssue化済みでない）コメントを取得
python3 scripts/fetch_drive_comments.py --course logic

# 2. Claude がJSONを読んで内容を評価し、templates/review-issue.md 形式の
#    findings.json を書く（comment_id / file_id は fetch の出力からそのまま転記）

# 3. 選んだものだけ Issue化。Driveのコメントへ「Issue化しました: <URL>」と返信し、
#    次回の fetch で重複提示されないよう .state/<course>/processed-comments.json に記録する
python3 scripts/promote_drive_comments.py --course logic --findings /path/to/findings.json --pick 1,3
```

認証は `update_drive.py` と同じ `GDRIVE_OAUTH_*` を使う。ローカル実行時に環境変数が
無ければ `~/.lecture-capture/config/drive-secrets.env` にフォールバックする
（lecture-capture-system と同一の Academic Materials Drive アカウントを共有しているため）。

## 英語学習機能（scripts/acenglish）

資料を「配って終わり」にせず、**その資料で英語を学び、詰まったところを資料の改善へ戻す**ための層。
設計の全体像は [`docs/2026-07-30-english-learning-integration.md`](docs/2026-07-30-english-learning-integration.md)。

```
sections/chNN-MM.md → 語彙・読解問題を生成 → ローカルUIで学習 → 回答・誤答を記録
   → 誤答原因を分類 → 学習者モデル更新 → 復習キュー
   → 同じ箇所で繰り返し間違えたら「資料の説明不足」として追記候補を立てる
   → findings.json → promote_drive_comments.py → Issue（既存の経路に合流）
```

### 使う

```bash
python3 -m pip install -r requirements-english.txt   # 初回だけ
scripts/english                                       # 学習UIを開く（127.0.0.1:8791）
scripts/english stop                                  # 止める
```

`scripts/english` は起動済みならブラウザを開くだけ。それ以外の引数は
`acenglish_cli.py` にそのまま渡る（`scripts/english status` など）。

初回の素材投入:

```bash
scripts/english fetch-toeic          # TOEIC語彙 2,282語。以後は不要（冪等）
scripts/english voa --limit 10       # 記事一覧 → --url で取り込み
```

出題は **期限が来た復習 → 未出題** の順で、種別（語彙・読解・文法）を1問ずつ混ぜる。
語彙が数千件あっても読解・文法が最初の数問で出てくる。UI 上部の選択で絞れる。

### 教材を増やす

```bash
scripts/english targets --course データ構造          # 学習対象を見る
scripts/english request --review-id dsa.ch02.list.s01 --out /tmp/req.json
#   → Claude が english/prompts/*.md に従って生成物を書く
scripts/english ingest --file /tmp/result.json      # 検証して取り込む
scripts/english findings --course dsa --out /tmp/findings.json
```

### 一般英語・TOEIC（科目資料以外の素材）

科目資料からは専門英語・論文読解しか作れない。一般英語と TOEIC には別の素材が要る。

```bash
python3 scripts/acenglish_cli.py fetch-toeic                 # 金フレ語彙 2,282語 (study-forge)
python3 scripts/acenglish_cli.py voa --limit 10              # VOA の記事一覧（PD）
python3 scripts/acenglish_cli.py voa --url <記事URL>          # 記事を学習対象に登録
python3 scripts/acenglish_cli.py ted --url <TED/YouTube URL> # 字幕のみ取得（音声は落とさない）
python3 scripts/acenglish_cli.py note-draft                  # 誤答 → ~/english-notes の drafts/
```

| 取得元 | 中身 | 生成の要否 |
|---|---|---|
| `study-forge` | TOEIC 語彙。`{term, definition, example}` が既にある | **不要**（そのまま語彙カード） |
| VOA Learning English | ESL 向けの平易な英文。米国政府著作物＝PD | 読解・文法・語彙を生成 |
| TED / YouTube | 字幕（`yt-dlp`、`--skip-download`） | 読解・語彙を生成 |

**市販の TOEIC 問題集からは問題文を取らない。** 権利のはっきりした英文を素材にして、
問題は自分の誤答傾向に合わせて生成する（`english/prompts/grammar.md` が Part 5 の作り方）。

外部素材には「直すべき章」が無いので、誤答が反復したときの行き先が科目資料と違う。

| 素材 | 反復誤答の行き先 |
|---|---|
| 科目資料 | `findings.json` → `promote_drive_comments.py` → GitHub Issue → PR |
| TOEIC / VOA / TED | [`~/english-notes`](https://github.com/yuta-u-tech/english-notes) の `drafts/` |

どちらも `drafts/` / Issue までで止まり、**`notes/` や章ファイルを直接書き換えない**。

### 置き場所の分担

| 何を | どこに | なぜ |
|---|---|---|
| 学習履歴・誤答・習熟度 | `~/.academic-english/english.db`（0700） | **このリポジトリは public**。`.gitignore` 頼みにしない |
| 英語ノート | [english-notes](https://github.com/yuta-u-tech/english-notes)（private） | 学習履歴と TOEIC 語彙由来の記述を含むため public にしない |
| 語彙の長期正本 | [goigoi-data](https://github.com/yuta-u-tech/goigoi-data)（private） | `word.schema.json` v1 が既に `source: academic` を想定済み |
| 正式な英語教材 | 科目リポジトリの `english/`（PR経由） | 「GitHub が唯一の正本、履歴は git」を英語教材にも適用する |
| Drive | 触らない | Drive は配布層。学習アプリは読み書きしない |

**生成の判断は Claude が担う。** どの語を選ぶか・どんな設問にするかは決定論コードで書けないため、
`request` で依頼を出し、`ingest` で検証して取り込む形にしてある（Drive コメント →
`findings.json` → Issue と同じ分担）。

**資料は無断で上書きしない。** 誤答から生まれるのは追記候補だけで、Issue 化するかは
`promote_drive_comments.py --pick` でユーザーが選ぶ。

## Academic Audio（scripts/academic_audio）

教材資産から、NotebookLM の Audio Overview に近い対話形式の学習音声を作る CLI 専用の
サブシステム。Web UI や配信処理には依存しない。責務は
`台本生成 → 音声生成 → 後処理 → ローカル一時出力` まで。

```bash
python3 scripts/academic_audio_cli.py doctor --json
python3 scripts/academic_audio_cli.py script generate \
  --review-id dsa.ch02.list.s01 --repo-root ../DataStructures
python3 scripts/academic_audio_cli.py generate \
  --review-id dsa.ch02.list.s01 --repo-root ../DataStructures --engine piper --mode fast \
  --piper-model .venv/piper-voices/en_US-lessac-medium.onnx
python3 scripts/academic_audio_cli.py job status <job-id>
python3 scripts/academic_audio_cli.py job resume <job-id>
python3 scripts/academic_audio_cli.py listening generate \
  --source english/chapter-03.md --engine piper --speeds 0.8,1.0,1.2 --listening-mode shadowing \
  --piper-model .venv/piper-voices/en_US-lessac-medium.onnx
```

TTS エンジンは共通インターフェースで扱う。`--engine` は
`auto | piper | style-bert-vits2 | wav`、`--mode` は `fast | balanced | quality`。
`wav` は外部 TTS なしでジョブ・キャッシュ・結合を検証するための内蔵レンダラ。

### Piper のセットアップ

```bash
python3 -m pip install -r requirements-audio.txt
python3 -m piper.download_voices en_US-lessac-medium --data-dir .venv/piper-voices
```

Piper 1.x は音声モデルが必須なので、`--piper-model <voice.onnx>` を渡す。渡さない場合は
`doctor` が `piper found, but no voice model` を返し、生成は走らない。話速は
`--speeds` / `--speed` から `piper --length_scale`（speed の逆数）へ渡す。
別の起動方法にしたいときだけ `--piper-command` に `{out}` などのテンプレートを渡す。

**Piper には日本語音声モデルが無い**（`download_voices` の一覧は en / zh / ko などのみ）。
日本語のテキストに英語モデルを使うと piper 自体は成功するが読み上げにならないため、
音声モデルの言語とセグメントの `language` が食い違う場合はエラーにしている。
したがって日本語の対話台本は Style-Bert-VITS2 を使う。

### Style-Bert-VITS2 のセットアップ

`scripts/style_bert_vits2_tts.py` が `style-bert-vits2` ライブラリのアダプタになっている。
音声モデルは JVNV（CC BY-SA 4.0）を使う。

```bash
python3 -m pip install -r requirements-audio.txt
python3 scripts/style_bert_vits2_tts.py download
```

バッチでは常駐モードを使う。1発話ごとにプロセスを起こすと毎回 BERT を読み直すため遅い。

```bash
python3 scripts/style_bert_vits2_tts.py serve --port 8787 &
python3 scripts/academic_audio_cli.py generate \
  --review-id logic.ch01.s01 --repo-root ../LogicCircuits \
  --engine style-bert-vits2 --mode quality \
  --style-bert-endpoint http://127.0.0.1:8787/render
```

1発話だけ確認したいときは `--style-bert-command` でもよい。

```bash
--style-bert-command "python3 scripts/style_bert_vits2_tts.py render \
  --output {out} --text {text} --speaker {speaker} --emotion {emotion} --speed {speed}"
```

台本の `speaker` は音声モデルへ、`emotion` は JVNV のスタイル
（`Neutral / Angry / Disgust / Fear / Happy / Sad / Surprise`）へ割り当てる。
既定の対応は `host` と `narrator` が `jvnv-F1-jp`、`learner` が `jvnv-M1-jp`。
`--voice-map "learner=jvnv-F2-jp"` で上書きできる。出力は 44100 Hz。

Style-Bert-VITS2 を自前で立てている場合は、WAV バイト列を返す任意の
`--style-bert-endpoint` を指定すればよい。ローカルの簡易確認用には macOS `say`
アダプタ（`scripts/macos_say_tts.py`）も使える。

```bash
--style-bert-command "python3 scripts/macos_say_tts.py --output {out} --text {text} --voice Kyoko"
```

`--mode quality` で Style-Bert-VITS2 が用意できていない場合は、黙って Piper に落とさずエラーにする。

成果物は既定で `.academic-audio/jobs/<job-id>/` に保存される。

| ファイル | 用途 |
|---|---|
| `dialogue.json` | speaker / text / language / emotion / speed / pause / source section を持つ台本 |
| `dialogue.md` | 人間が確認しやすい台本 |
| `segments/*.wav` | 発話単位の音声 |
| `output.wav` | 結合済みローカル成果物 |
| `job.json` | 進捗、失敗セグメント、再開用メタデータ |

## テスト

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest tests/
```

英語学習機能のテストは `requirements-english.txt` の依存も要る（`fastapi` / `pydantic`）。
