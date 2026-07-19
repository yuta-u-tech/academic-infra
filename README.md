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

## テスト

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest tests/
```
