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

`update_drive.py` はサービスアカウントを使う。科目リポジトリに次の Secret を設定する。

| Secret | 内容 |
|---|---|
| `GDRIVE_SERVICE_ACCOUNT_JSON` | サービスアカウントの JSON（パスではなく中身） |
| `GDRIVE_PARENT_FOLDER_ID` | Drive の親フォルダ（`Academic Materials`）の ID |

親フォルダをサービスアカウントのメールアドレスに **編集者** として共有しておく。
Secret 未設定なら Drive 同期はスキップされ、成果物は Actions の Artifact から取れる。

将来的には OIDC + Workload Identity Federation に移行し、長期鍵を持たない。
