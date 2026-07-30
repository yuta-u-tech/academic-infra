"""英語学習機能（academic-infra の学習側拡張）。

academic-infra 本体（`acinfra`）が「TeX を成果物へビルドして Drive へ配る」層なのに対し、
ここは「その成果物で学習し、結果を資料の改善へ還流させる」層を担う。

設計上の分担は `docs/2026-07-30-english-learning-integration.md` を正とする。要点だけ:

- 学習履歴・誤答・習熟度は **このリポジトリに置かない**。academic-infra は public なので、
  実体は `~/.academic-english/english.db`（リポジトリ外・0700）に置く。
- 生成物の長期正本は GitHub（科目リポジトリの `english/` と goigoi-data）。Drive へは書かない。
- 資料の修正は既存の findings.json → `promote_drive_comments.py` → Issue 経路に合流させる。
  ここから科目リポジトリへ直接書き込むことはしない。
"""
