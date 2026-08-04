# 目標駆動型学習オペレーション基盤の設計（Issue #4・現状接地版）

> ステータス: **設計（Phase 1着手前）**。Issue #4 本文の設計をこのリポジトリの実体に接地し、
> 何が既にあり・何が無いかを確定した上で、Phase 1 の着手順を決める。
> 実装は本ドキュメントの対象外（§9・§10 参照。着手は別 Issue に分割する）。
> 最終更新: 2026-08-04

---

## 0. 結論（先に）

Issue #4 は Goal Engine / Planning Engine / Resource Intelligence / Research Intelligence を
まっさらな状態から作る前提で書かれているが、**Evidence Engine と Mastery Engine は
`scripts/acenglish/` に既に実装済み**（英語ドメインに閉じた形で）。これを Core へ格上げせず
作り直すと、English Learning Integration 設計（`docs/2026-07-30-*.md`）と同じ二重実装の罠に落ちる。

→ 方針: **`acenglish` の Evidence/Mastery を Core の実装として再利用し、その上に
Goal / Competency / Resource / Research の各層を新設する。** TOEIC Domain Plugin は
「新規に作る」のではなく「`acenglish` を Core Interface に適合させる」形になる。

もう一つ、Issue #4 本文は `gjp` と `pm-desk` の存在を前提にしているが、**このセッションの
アクセス範囲は `academic-infra` 単体**であり、`yuta-u-tech` 配下のリポジトリ一覧に `gjp` と
一致する名前が見当たらない（§8.1 で確認事項として明記）。そのため本設計は
**academic-infra 側は CLI と JSON 出力までを責務とし、gjp/pm-desk 側の表示・統合は
別リポジトリ側の作業として境界を切る**（Issue #4 自身の「Operations」節の分担方針と一致）。

---

## 1. 現状分析

### 1.1 このリポジトリの実体（再確認）

`README.md` が明記する通り、academic-infra は**TeX ビルド・配布基盤**であり、
`courses.yml` の7科目（dsa / statistics / logic / circuit / llm / modern-legal-issues /
modern-astronomy）はいずれも「Goal」ではなく「講義資料の配布単位」でしかない。
Goal・Milestone・優先度・期限という概念はどこにも存在しない。

### 1.2 `acenglish`: Evidence/Mastery Engine は実装済み（英語ドメイン限定）

`docs/2026-07-30-english-learning-integration.md` の実装により、以下は**既にある**。

| Issue #4 が要求するもの | 現状の実装 |
|---|---|
| StudyItem 境界 | `acenglish/items.py`: `VocabItem` / `ReadingItem` / `GrammarItem`（`kind` で判別する Pydantic モデル） |
| Evidence（正誤以外の観測値） | `acenglish/db.py` の `attempt` テーブル: `correct` / `elapsed_ms` / `self_confidence` / `hint_used` / `retry_count` / `error_cause` / `edit_distance` / `days_since_last` |
| Mastery Engine（正答率で表さない） | `acenglish/model.py`: `response_quality()` がヒント・遅さ・自信度を割り引き、`skill_state.mastery` を更新 |
| 忘却・復習間隔 | `acenglish/model.py`: SM-2（goigoi と同一実装） |
| 誤答原因の6分類 | `acenglish/diagnose.py`: `knowledge_gap` / `material_gap` / `production_gap` / `vocabulary_gap` / `parsing_gap` / `speed_gap` |
| 教材不足の検出→提案 | `diagnose.escalate()`（同一箇所3回連続の `knowledge_gap` で `material_gap` に昇格）→ `revision_candidate` テーブル |
| 提案の外部化 | `acenglish/promote.py` → 既存 `promote_drive_comments.py` 相当の経路で `findings.json` → GitHub Issue |
| 生成物の出所追跡 | `generated_item.generated_by` / `prompt_version` / `source_commit`（Issue #4 の Intervention の一部を先取り） |

`skill_state` の主キーは `(domain, sub_skill, target_ref)` で、`target_ref` は現状 `review_id`
（科目資料）または語彙IDに限定されている。**Goal と紐付ける概念が無い**のがギャップ。

### 1.3 `academic_audio` / `toeic_reading`: 生成専用、学習ループに未接続

`academic_audio/items.py`（`ListeningItem` / `PassageSet` 等）と `toeic_reading/render.py` は
TOEIC Part 1–5 相当の**教材生成と冊子/Drive投稿**のみを行う。`attempt` を書かない、
`skill_state` を読まない。Issue #4 背景の「`academic_audio` と `acenglish/study.py` が
未接続」は現時点でもそのまま当てはまる。

生成された `ListeningItem` / `GrammarItem` には Issue #4 が言う「学習ループへ渡す共通形式」に
必要な `competency_ids` に相当するフィールドが無い（`domain` / `sub_skill` はあるが、
Part番号や TOEIC 固有の taxonomy が無い）。

### 1.4 存在しないもの（Issue #4 の要求のうち純粋に新規）

- Goal / Milestone / 親子Goal / 優先度 / 期限
- Competency Graph（Skill/Subskill の前提関係。`skill_state` はフラットな集計先であって
  グラフ構造ではない）
- Resource Registry / Resource Requirement（教材の所有・権威性・状態を持つ台帳）
- Research Request / Finding
- 制約付き Weekly Planner（Google Calendar / gjp からの時間制約取得を含む）
- Weekly Review 生成（12セクション、Goal Health）
- Proposal / Approval の3層（自動実行可能・提案のみ・明示的承認必須）— 現状は
  `material_gap` の revision_candidate のみで、これは「提案のみ」層1種類しか無い
- Intervention（何を変更したか・理由・根拠・承認者・期待効果・実際の結果）の追跡
- `academic-infra goal/plan/report/resources/research/proposal` CLI 群
- gjp / pm-desk との連携経路（このセッションからは gjp の実体を確認できていない）

### 1.5 goigoi との整合（既存の制約、引き続き有効）

`skill_state` の SM-2 は goigoi と同一実装という制約が既にある（§1.2 参照）。
Goal 層を新設しても、既存の間隔計算・`review_id` 体系・`~/.academic-english/english.db` の
スキーマは変更しない。壊すと goigoi-data 同期が壊れる制約は Issue #4 でも継続する。

---

## 2. アーキテクチャ方針

### 2.1 Core の置き場所: 新設 DB + 既存 DB の参照、統合はしない

`~/.academic-english/english.db` を Core 化して全ドメインに広げるのは誤り
（TOEIC 以外のドメイン、例えば統計検定を英語アプリの DB に混ぜる理由が無い上、
`academic-infra` は public リポジトリで個人データを一切置けないという制約が
`~/.academic-english/` の外出しの理由そのものだったため、Core も同じ制約を継承する）。

```
~/.academic-infra/                  ← 新設（リポジトリ外・0700）。Core の運用状態
└── core.db                         ← Goal / Milestone / Competency / Resource /
                                       ResearchRequest / Plan / Proposal / Intervention

~/.academic-english/english.db      ← 既存のまま。Evidence/Mastery/Attempt はここに残す
```

Core の `competency` テーブルは `domain_ref`（例: `acenglish` の `(domain, sub_skill,
target_ref)` 3つ組、または科目資料の `review_id`）を**外部キーではなく緩い参照**として持つ。
Core は Domain Plugin の DB に直接 JOIN しない（DB エンジンをまたぐ上、Domain Plugin ごとに
スキーマが違うため）。Domain Plugin 側が Core Interface（§2.3）経由で mastery 集計値を返す。

これは Issue #4 の設計原則1「Academic Infraが状態と規則を保持する」を、
「Core が Evidence の正規データを直接持つ」ではなく「Core が Goal/Competency/Resource の
正規データを持ち、Evidence の正規データは Domain Plugin が持つ」という形で実装する、
という意味になる。Issue #4 本文の共通データモデル図はこの分離を明示していないため、
**ここが本文からの明確な補強点**。

### 2.2 バックアップ・正本

`academic-english-data`（private）と同じパターンで、`academic-infra-data` のような
private リポジトリを Core の `core.db` バックアップ先として使う（新規リポジトリ作成は
このドキュメントの範囲外。Phase 1 着手時に確認する）。

### 2.3 Domain Plugin Interface（最小形）

Issue #4 の Domain Plugin Interface を、今ある2つの実装（acenglish が実質1つ目、
academic_audio が2つ目候補）から逆算して最小定義する。

```python
class DomainPlugin(Protocol):
    domain_id: str  # "toeic" など。competency_id の namespace になる

    def competencies(self) -> list[Competency]: ...
    def to_study_items(self, source: Any) -> list[StudyItem]: ...
    def mastery_summary(self, competency_ids: list[str]) -> dict[str, MasterySummary]: ...
    def resource_gap_hint(self, competency_id: str) -> ResourceGapHint | None: ...
```

`acenglish` は `mastery_summary` を `skill_state` からそのまま返せる（新規実装ほぼ不要）。
`academic_audio` は `to_study_items` を実装する必要がある（Issue #4 の TOEIC実証優先順
の3番目そのもの）。

---

## 3. データモデル（Core・Phase 1 スコープ）

Issue #4 §「共通データモデル」のうち、Phase 1 完了条件（§9 完了条件参照）に必要な分だけを
`core.db` の DDL 相当で確定する（実装せず、設計として固定する）。

```sql
-- ID は既存の REVIEW-ID 方式（ドット区切り・不変）を踏襲する。新体系を作らない。
CREATE TABLE goal (
    goal_id       TEXT PRIMARY KEY,   -- 例: "toeic-900"
    parent_goal_id TEXT,              -- 例: 親 "grad-school-admission"
    title         TEXT NOT NULL,
    target_value  TEXT,               -- 例: "900"
    current_value TEXT,
    deadline      TEXT,
    priority      INTEGER NOT NULL DEFAULT 3,
    evaluation_method TEXT,
    status        TEXT NOT NULL DEFAULT 'active',  -- active/paused/achieved/abandoned
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE competency (
    competency_id TEXT PRIMARY KEY,   -- 例: "toeic.part7.double"（namespace = domain_id）
    goal_id       TEXT NOT NULL REFERENCES goal(goal_id),
    domain_id     TEXT NOT NULL,      -- "toeic" 等。Domain Plugin の namespace
    parent_competency_id TEXT,        -- Skill/Subskill の前提関係
    title         TEXT NOT NULL,
    domain_ref    TEXT,               -- Domain Plugin 側の (domain,sub_skill,target_ref) をJSON文字列で
    exam_weight   REAL,
    created_at    TEXT NOT NULL
);

CREATE TABLE resource (
    resource_id   TEXT PRIMARY KEY,
    goal_id       TEXT NOT NULL REFERENCES goal(goal_id),
    title         TEXT NOT NULL,
    kind          TEXT NOT NULL,       -- book/pdf/generated/app 等
    location      TEXT,                -- Drive file_id 等
    status        TEXT NOT NULL DEFAULT 'candidate',  -- candidate/reviewed/active/deprecated/archived
    authority     TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE resource_requirement (
    requirement_id TEXT PRIMARY KEY,
    goal_id        TEXT NOT NULL REFERENCES goal(goal_id),
    competency_ids TEXT NOT NULL,       -- JSON配列
    gap_kind       TEXT NOT NULL,       -- coverage/difficulty/activity/quality/evidence/volume/freshness
    priority       TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'unresolved',
    spec           TEXT NOT NULL,       -- YAML/JSON。Issue #4 のresource_requirement例をそのまま
    created_at     TEXT NOT NULL
);

CREATE TABLE research_request (
    request_id    TEXT PRIMARY KEY,
    goal_id       TEXT NOT NULL REFERENCES goal(goal_id),
    kind          TEXT NOT NULL,        -- goal_definition/competency_discovery/... (Issue #4の8種)
    trigger       TEXT NOT NULL,        -- 何が発行させたか
    status        TEXT NOT NULL DEFAULT 'open',
    created_at    TEXT NOT NULL
);

CREATE TABLE finding (
    finding_id    TEXT PRIMARY KEY,
    request_id    TEXT NOT NULL REFERENCES research_request(request_id),
    summary       TEXT NOT NULL,
    proposal_kind TEXT NOT NULL,        -- competency_update/resource_candidate/... 等
    payload       TEXT NOT NULL,        -- JSON
    created_at    TEXT NOT NULL
);

CREATE TABLE proposal (
    proposal_id   TEXT PRIMARY KEY,
    goal_id       TEXT NOT NULL REFERENCES goal(goal_id),
    tier          TEXT NOT NULL,        -- auto/suggest/approval_required（Issue #4の3層）
    kind          TEXT NOT NULL,
    payload       TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',  -- pending/approved/rejected/expired
    reason        TEXT,
    approved_by   TEXT,
    approved_at   TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE intervention (
    intervention_id TEXT PRIMARY KEY,
    goal_id         TEXT NOT NULL REFERENCES goal(goal_id),
    change_summary  TEXT NOT NULL,
    reason          TEXT NOT NULL,
    evidence_ref    TEXT,               -- finding_id / revision_candidate id 等
    approved_by     TEXT,
    expected_effect TEXT,
    actual_effect   TEXT,
    confidence      TEXT,               -- 効果の確度（相関≠因果を明示するため必須）
    created_at      TEXT NOT NULL
);
```

`attempt` / `skill_state` / `revision_candidate` は複製しない。Core はこれらを
Domain Plugin Interface 経由で読むだけ。`competency.domain_ref` が `acenglish` の
`skill_state` 主キーへの橋渡しになる。

---

## 4. ディレクトリ構成（Phase 1 実装時の見取り図）

```
scripts/
├── acenglish/          既存。Domain Plugin「toeic/english」を後付けで実装する対象
├── academic_audio/     既存。to_study_items() を実装する対象
├── toeic_reading/       既存
├── acinfra/             既存（TeXビルド）
└── acinfra_core/        新設
    ├── db.py             core.db 初期化・マイグレーション（acenglish/db.py と同型）
    ├── models.py         Goal/Competency/Resource/...（Pydantic、§3のDDLに対応）
    ├── goal.py            Goal Engine
    ├── plan.py            Planner（Phase 3）
    ├── resource.py         Resource Intelligence
    ├── research.py         Research Intelligence
    ├── report.py           Weekly Review 生成
    ├── proposal.py         Approval/Audit
    └── plugins/
        ├── base.py         DomainPlugin Protocol（§2.3）
        └── toeic.py         acenglish + academic_audio を束ねるアダプタ

docs/schema/              core.db 相当の JSON Schema（english/schema/ と同じ思想）
bin/academic-infra         CLI エントリポイント（Issue #4 のCLI候補节）
```

---

## 5. 承認フロー・Audit の再利用

Issue #4 の3層はそのまま採用するが、**「提案のみ」層は revision_candidate の仕組みを
一般化するだけで実装できる**（新規に作るのは分岐先の種類だけ）。

| Issue #4 の層 | 実装 |
|---|---|
| 自動実行可能 | `skill_state` 更新・復習追加は既存のまま（Core を経由しない） |
| 提案のみ | `proposal` テーブル（`tier='suggest'`）。`revision_candidate` は既にこの型の一種として存在するので、`acenglish.diagnose.open_revision_candidate` を `proposal` 発行の一実装として位置付ける |
| 明示的承認必須 | `proposal` テーブル（`tier='approval_required'`）。CLI `academic-infra proposal approve` が `approved_by`/`approved_at` を埋める |

Intervention は「承認された proposal が実際に適用された記録」として `proposal` から
1:1 で派生させる（Issue #4 の「因果と断定しない」要件のため `confidence` を必須にする）。

---

## 6. Weekly Review・Ops 統合の境界

Issue #4 は「新規ダッシュボードを作らず gjp/pm-desk の既存導線へ統合する」としているが、
**このセッションでは `gjp` に一致するリポジトリを確認できていない**（§8.1）。
そのため設計としては、academic-infra 側の責務を次で止める。

- `academic-infra report weekly --goal <id>` が JSON（Issue #4 の12セクション相当）を吐く
- gjp / pm-desk 側がそれを読んで表示する（表示側の実装は各リポジトリ側の Issue）

これにより、gjp の実体が不明でも academic-infra 側は自己完結してテスト可能になる。

---

## 7. TOEIC Domain Plugin: 実装順の補正

Issue #4 の「TOEIC実証の優先順」は Evidence/Mastery が無い前提のリストになっている。
実際は §1.2 の通りかなりの部分が既にあるため、次の順に補正する。

1. ~~共通StudyItemスキーマ~~ → **既存 `acenglish/items.py` を Core の StudyItem 契約に合わせて薄く拡張**（`competency_ids` フィールド追加）
2. TOEIC Part / Skill / Subskill taxonomy → **新規**（`acinfra_core/plugins/toeic.py` の `competencies()`）
3. `academic_audio` → StudyItem変換 → **新規**（Part1–4がまだ学習ループに未接続なのはIssue本文の指摘通り）
4. StudyItem → `acenglish/study.py` 接続 → Part3で生成したStudyItemを`generated_item`に取り込む変換のみ（`attempt`/`skill_state`ロジックは流用、新規実装ではない)
5. attempt / evidence / mastery更新 → **既存のまま流用**（新規実装ゼロ）
6. Goal / Competency 層の新設 → **新規**（§3のcore.db）。Issue本文には無いが、これが無いと7以降が意味を持たない
7. 教材Registryと不足診断 → **新規**（`resource.py` / `resource_requirement`）
8. 公式問題集プロファイル取り込み → 保留（Issue #4 §非目標に抵触しない範囲の確認が要る。市販教材の権利問題は `docs/2026-07-30-*.md` §12 の既存方針＝問題文を複製しない、を継承）
9. Part 6 / Part 7生成 → 保留（Part1–5の学習ループ接続が先）
10. gjp ロールアップ → **保留**（§8.1 の確認待ち）
11. 週次レポート → §6 の範囲でacademic-infra側のみ新規実装
12. 模試較正 → Phase 4 相当、保留

---

## 8. 未着手・要確認事項

### 8.1 gjp の実体確認（ブロッカー）

`mcp__Claude_Code_Remote__list_repos` で `yuta-u-tech/*` を確認したが `gjp` と一致する
リポジトリ名が見当たらない（近そうなのは `progress-ledger` / `yaruki` / `personal-pm-agent`
だが、Issue #4 本文の「gjp web」「Google Calendarやgjpから時間制約を取得」という記述と
一致するか未確認）。Phase 3（Planner）着手前に確定させる必要がある。

### 8.2 Core の保存先リポジトリ

`~/.academic-infra/core.db` のバックアップ先 private リポジトリ（`academic-infra-data` 等）を
新規作成するかどうか。`academic-english-data` と同じパターンで進めてよいか確認したい。

### 8.3 Phase 1 実装の Issue 分割

本ドキュメントは設計のみで、コード変更を含まない。Issue #4 の Phase 1 チェックリストは
本ドキュメント §3〜§4 に対応する形で、実装は別 Issue（`acinfra_core` 新設 / TOEIC Plugin化 /
Resource Registry の3つ程度）に分割することを提案する。1 Issue で Phase 1 全体を実装すると
レビュー困難な巨大PRになる。

### 8.4 公式問題集プロファイル取り込みの権利確認

§7 の8番目。`docs/2026-07-30-*.md` の既存方針（問題文を複製しない、TOEIC語彙はpublicリポジトリに
書かない）を Part 6/7 にも適用する前提で問題ないか、着手時に再確認する。

---

## 9. この Issue での完了条件との対応

Issue #4 の「完了条件」1〜7 は Phase 1〜3 全体の完了を指すため、本ドキュメント単体では
満たされない。本ドキュメントが確定するのは以下のみ:

- [x] Core と既存 acenglish の責務分離（§2.1）
- [x] Domain Plugin Interface の最小形（§2.3）
- [x] Phase 1 データモデル（§3）
- [x] TOEIC実証の実装順の補正（§7、既存実装分の重複回避）
- [ ] 完了条件1〜7の実装（別 Issue、§8.3）

---

## 10. 非目標（このドキュメントの範囲外）

- コード実装（`acinfra_core` の新規作成を含む一切のコード変更）
- gjp / pm-desk リポジトリ側の変更（アクセス確認ができていない上、責務外）
- Statistics / Logic Circuit / Mathematics / Programming Domain Plugin の設計（TOEIC実証が先という Issue #4 自身の方針に従う）
- MCP化（Issue #4 自身が「安定後」としており、CLIすら未実装の現時点では時期尚早）
