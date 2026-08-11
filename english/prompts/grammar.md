# 空所補充の文法問題の生成（prompt_version: 2026-07-30.1）

依頼 JSON の `material` を読み、**TOEIC Part 5 と同じ形**の空所補充問題を作る。出力は
`english/schema/generation-result.schema.json` に準拠した JSON 1ファイル。

市販の問題集から問題文を写さない。素材（VOA の記事・TED の字幕・TOEIC 語彙）に出てくる
語と場面を使って、こちらで作る。

## 難易度の目標（900点、990点ではない）

TOEIC900点は「Part5の正答率8割を超えている」帯にあたる（`900点特急 パート5&6` の対象読者
記述）。この帯で外してはいけないのは**「品詞の形さえ知っていれば意味を読まなくても解ける
問題（600点レベル）を、パターンに関わらず作らない」**という一点。パターンの割合を歪める
ことではなく、**どのパターンでも空所の直前直後だけでなく文全体を読まないと絞れない設計に
する**ことが本質（較正ログ2026-08-05参照）。

### 実際のPart5の構成比（複数の対策サイトの集計、ETS非公開のため目安）

| タイプ | 割合の目安 | 対応パターン |
|---|---|---|
| 品詞問題（名詞/動詞/形容詞/副詞の識別） | 約20〜30% | パターンA |
| 語彙問題（単語の意味の識別） | 約25〜30% | パターンB |
| 前置詞・接続詞・語法（コロケーション） | 約10〜20% | パターンC |
| 時制・態・不定詞・動名詞等 | 約10〜20% | パターンA寄り |

情報源によって「品詞問題が最多」派と「語彙問題が最多」派に分かれ断定はできないが、
**文法系（品詞+前置詞+時制、A寄り）で約7割、純粋な語彙問題（B）で約3割**という大枠は
複数ソースで一致している。**900点との相関が最も強いのはパターンC（前置詞・語法の
コロケーション）**——複数の情報源で「Part5で最も差がつく型」「860点以上は最後の
難しい語法まで取り切る精度が必要」と説明されている。

### 1日あたりの出題

**既定は「通常30問＋苦手重点20問」の合計50問**（2026-08-05にこの2段構成へ変更）。
1〜30問目は下記の通常配分（A:B:C ≒ 10:9:11）。31〜50問目は直近の誤答を踏まえた
重点問題で、以下の手順で作る。

1. `python3 scripts/toeic_reading_cli.py weak-points --limit 30` を実行する。
   Part5の直近の誤答が `point`/`pattern`/`pattern_note`/実際の文・選択肢つきで
   時系列順（新しい順）に返る。**集計・分類はしていない生データなので、
   どれを重点的に再出題するかは Claude が読んで判断する。**
2. 出力から「同じ語・同じ文法項目で複数回間違えている」「直近のセットで間違えた」
   ものを優先し、20問分の対象（語彙・コロケーションペア・文法項目）を選ぶ。
   1回しか出ていない誤答でも、直近（同じ日〜前日）のものは優先してよい。
   全く同じ文の使い回しはしない（新しい文脈で再出題する）。
3. 対象が20問に満たない場合（学習を始めたばかりでまだ誤答データが少ない場合）は、
   残りを通常配分と同じ考え方（A:B:C配分、パターンC厚め）で埋めてよい。
   `weak-points` が0件（初回など）なら、31〜50問目も通常30問と同じ配分で作る
   （＝実質60問構成になるが、それでよい。無理に「苦手」を捏造しない）。
4. 31〜50問目の `pattern_note` の末尾に「（苦手重点: 20260805の誤答を踏まえて再出題）」
   のように、どの日の誤答を踏まえた再出題かを一言添える。後から
   「重点問題がどれだけ定着したか」を`explanation`やログから追えるようにするため。

このITEMS.JSON全体（1〜50問）は1つのファイルとして扱う。**書いた直後、`worksheet`/`ingest`/
Form作成のいずれよりも前に、必ず `toeic_reading_cli.py shuffle --items items.json` を実行して
設問順序を機械的にシャッフルすること。** 前半30問＝通常・後半20問＝苦手重点という順のまま
出題すると、出題順から「これは復習問題だ」と分かってしまう（2026-08-09、ユーザー指摘）。
シャッフル後は`worksheet`/`publish`/`ingest`をこれまで通り1回ずつ実行すればよい
（件数が増えるだけで手順自体は変わらない）。review_idはシャッフル後の並び順に基づいて
割り当てられるため、shuffleは必ずingestより前に行う。

### 較正ログ

- 2026-08-05: パターンBの初回セット（`affect/effect`等、パターンA 1問・パターンB 4問）を
  出題したところ5問全問正解。「もっと難しくてよい」とのフィードバックを受け、パターンB+Cを
  7割以上にする方針に変更 → `complimentary/complementary`等のパターンBと、
  `raise concerns`/`meet the deadline`のパターンCを増やした2セット目を出題し好評だった。
- 2026-08-05（同日、追加調査後）: しかし実際のPart5の構成比を調べたところ、
  **文法系（パターンA寄り）が全体の約7割を占めており、パターンAを減らす方針は
  実際の出題傾向と逆だった**と判明。900点で変わるのは「パターンAの比率を下げる」ことでは
  なく「パターンAも含めて全パターンを文全体読解が要る難度にする」こと、かつ
  「900点の分かれ目であるパターンC（語法・コロケーション）を厚めに配分する」ことだと結論。
  → 以後は実際の構成比に近い配分（A寄り7割・B3割の実態から、Cを意図的に厚くした
  A:B:C ≒ 10:9:11、1日30問）に変更する。
- 2026-08-05: 「作ってと指示された時に、生成→PDF組版→学習ループ取り込み→Drive投稿まで
  確認なしで一気通貫実行する」方針に確定（cronでの定時実行ではない）。毎回同じ語彙・
  コロケーションが重複しないよう「使用済み語彙・コロケーションログ」を新設し、生成の
  たびに追記する運用に変更。
- 2026-08-05: 初回の実解答ログ（20260805d、30問中21正解・7誤答）で、誤答が
  `to不定詞`/`仮定法現在`/`adapt-adopt`/`place an order`等のパターンC寄りコロケーションに
  集中していることが判明。ユーザーから「通常30問＋苦手重点20問」の2段構成にする提案があり、
  採用。誤答データの取得元として `toeic_reading_cli.py weak-points` を新設した
  （集計はせず生データを返すだけ。判断はClaude側）。
- 2026-08-09: 解答提出をGoogle Formsに切り替え（`toeic_forms_cli.py`）。設問データ生成
  →Form作成→TeX（冊子先頭に`\href{}`でFormリンクを1回だけ埋め込み）→PDF→Drive公開、
  という順で一気通貫実行する運用に変更（詳細は`docs/2026-08-09-toeic-forms-integration.md`）。
  この日の20260805分の`weak-points`（8件、`目的を表す不定詞`/`仮定法現在`/`adapt-adopt`/
  `place an order`/`issue a refund`/`extend an invitation`/`renew a contract`/`raise-rise`）
  を苦手重点20問に反映した初回セット。
- 2026-08-10: `weak-points --limit 30`で19件の誤答（20260805d/20260809分）を確認し、
  頻出（3回: `extend an invitation`のC、2回: `目的を表す不定詞`のA・`adopt/adapt`のB）を
  優先して苦手重点20問に反映。shuffle実行後、通常30問（A11:B9:C10）と合わせて
  review_id `toeic.part5.20260810.0001`〜`0050`で一気通貫実行（Form作成→PDF→Drive公開→
  ingestまで完走）。
- 2026-08-11: ユーザー指摘で`toeic.part5.20260810.0005`（regardless/despite/in spite/
  notwithstanding、空所直後に`of`）の解説誤りを発見・修正（DBの`generated_item.payload`を
  直接更新）。空所直後に`of`が既にあるのに「in spiteは単独でofを伴わないため誤り」と
  書いており、実際には`in spite of`として文法的に成立してしまっていた（pattern_note内でも
  「in spite ofは成立する」と自己矛盾）。正解(regardless)自体は変わらないが、除外理由を
  文法ではなく意味（区分を表す中立語か、逆境を表す語か）に書き直した。詳細は上の「制約」節。

### 使用済み語彙・コロケーションログ（パターンB/C、重複回避用）

**新しいセットを作るたびに、このリストに無い組を優先し、使ったものをここに追記する。**

- パターンB（似ているが別の語）: `affect`/`effect`, `raise`(他動詞)/`rise`(自動詞),
  `assure`/`ensure`/`insure`, `economic`/`economical`, `complimentary`/`complementary`,
  `principal`/`principle`,
  `considerable`/`considerate`, `eligible`/`legible`, `respective`/`respectful`,
  `adapt`/`adopt`, `assess`/`access`, `advice`/`advise`, `personal`/`personnel`,
  `continuous`/`continual`, `industrial`/`industrious`, `comprehensive`/`comprehensible`,
  `confidential`/`confident`, `successive`/`successful`, `efficient`/`sufficient`,
  `exhaustive`/`exhausted`, `stationery`/`stationary`, `credible`/`creditable`,
  `respective`/`respectable`/`respectful`/`respected`（2026-08-09追加）,
  `methodical`/`methodological`, `overview`/`oversight`, `secure`/`secured`,
  `lengthy`/`length`/`lengthen`, `discrepancy`/`discretion`, `reassure`/`assure`/`ensure`/`insure`,
  `remarkable`/`remarkably`, `divergent`/`diverse`（2026-08-10追加）
- パターンC（コロケーション）: `raise concerns`, `meet the deadline`, `place an order`,
  `conduct a survey`, `reach a consensus`, `submit an application`, `issue a refund`,
  `extend an invitation`, `address a complaint`, `renew a contract`, `postpone`（文脈適合）,
  `implement a policy`, `terminate a contract`, `forfeit a deposit`, `allocate a budget`,
  `process a complaint`, `exceed expectations`, `reach an agreement`, `grant an extension`
  （2026-08-09追加）,
  `raise funds`, `draw attention`,
  `convene a meeting with`, `draft a proposal`, `secure funding`, `waive a fee`,
  `honor a warranty`, `void a contract`, `streamline a workflow`, `mitigate a risk`,
  `expedite a shipment`, `curb spending`（2026-08-10追加）

## sentence

- 1文。空所は `____`（アンダースコア4つ）ちょうど1箇所。
- 素材に出てきた語・話題を使う。素材と無関係な一般例文で埋めない。
- ビジネス文脈（会議・注文・出張・人事）を優先する。TOEIC の出題場面がそこに偏るため。
- **パターンに関わらず、空所の直前直後の1〜2語だけを見て解けるほど短い・単純な文にしない。**
  従属節・関係詞節・時を示す副詞句などで、文全体を読まないと正しい形/語が決まらないように
  構成の一部を長くする。

## choices / answer_index

- 4択が基本（3–5択まで可）。`answer_index` は 0 始まり。
- ランダムな無関係語を混ぜない。1つでも混ざると消去法で解けてしまう。
- 誤答選択肢は次の3パターンのいずれかで作り、`pattern` フィールドに `A`/`B`/`C` を、
  `pattern_note` にどう分類したかの理由を必ず書く（下記「pattern / pattern_note」参照）:
  - **パターンA（同じ語の別の形）**: 品詞・時制・態など。「意味を知っているか」ではなく
    「形を選べるか」を問う。
    - 品詞: `succeed` / `success` / `successful` / `successfully`
    - 態・時制: `has completed` / `was completed` / `completing` / `to complete`
    - 前置詞・接続詞: `despite` / `although` / `because of` / `however`
    - 実際のPart5でも約7割を占める主力パターンなので、数を絞りすぎない。ただし
      sentenceの節で述べた通り、文全体を読まないと形が決まらない長さ・複雑さにする。
  - **パターンB（似ているが別の語）**: 「形が同じでも意味・品詞が違う語」「スペルや音が
    近い別の語」を混ぜ、意味を読まないと絞れない形にする。
    - 新しい組を選ぶときは、下の「使用済み語彙・コロケーションログ」に無いものを優先する。
    - 語幹まで似た低頻度語（990点向け、例: `inversion/intrusion/aversion/invasion`）は
      出しすぎない。ビジネス語彙の範囲に収める。
  - **パターンC（コロケーション知識）**: 文法的にはどれも成立しうるが、その語と実際に
    結びつく語（動詞+名詞、動詞+前置詞、形容詞+名詞 等）の知識だけで正誤が決まる形にする。
    誤答は「意味は近いが結びつきとしては不自然な語」にする（例: `raise funds` に対し
    `lift/elevate/hoist` のような物理的に「持ち上げる」意味の語を誤答にする）。
    **正解が2つ成立しないよう、誤答は同じ意味分野でも明確に結びつかない語を選ぶ**
    （「reach/achieve consensus」のようにどちらも正しい類義語コロケーションになる
    組み合わせは避ける）。`explanation` には**なぜその組み合わせが自然/不自然か**を、
    文法規則ではなく「実際にそう使われるから」という形で書く。**900点との相関が最も
    強いパターンなので、実際の構成比（10〜20%）より意図的に厚めに配分する。**
    新しいコロケーションを選ぶときは、下の「使用済み語彙・コロケーションログ」に
    無いものを優先する。

## point / pattern / pattern_note

- `point`: 問われている文法・語彙項目を短く書く（`副詞と形容詞の区別` /
  `principalとprincipleの混同` / `raise concernsのコロケーション`）。
  **誤答が同じ `point` に集中したとき、文法ノートのどこを書き足すべきかがこれで決まる**ので、
  「文法」のような粗い書き方をしない。
- `pattern`: `A`/`B`/`C` のいずれか（上の「choices / answer_index」の分類に対応）。
- `pattern_note`: なぜそのpatternに分類したかを1〜2文で書く（例:
  「選択肢が同じ語幹raiseの活用ではなく、意味の近い別の動詞との使い分けを問うためB」）。

## explanation

正解の理由に加えて、**各誤答がなぜ入らないかだけでなく、その語/形が正しくはどう使われるか**を
1つずつ書く。「不正解」を伝えるだけでは、次に別の文でその語に出会っても使い分けられるように
ならない。誤答のたびに知識が1つ増える解説にする。

- **パターンA**: 誤答が同じ語の別の形（品詞・時制等）なら、それぞれの形が**正しく使われる
  別の文脈・例**を短く示す（例: `completing` は「動名詞または現在分詞として使う。
  例: completing the form takes five minutes.」）。
- **パターンB**: 誤答が似ているが別の語なら、その語の**本来の意味と正しい用例**を示す
  （例: `complementary` なら「『補完的な』という意味。例: complementary skills（補完し合う
  スキル）」）。
- **パターンC**: 誤答の語がなぜこの語と結びつかないかに加え、**その語が実際にはどんな語と
  結びつくか**（正しいコロケーション例）を示す（例: `hold` なら「hold a meeting/hold an
  election のように使う。consensusとは結びつかない」）。
- 長くなりすぎないよう、誤答1つにつき1文程度（`explanation` 全体で2000字以内に収める）。

## sub_skill

| 値 | どういう問題か |
|---|---|
| `knowledge` | 規則そのものを知っているかを問う |
| `recognition` | 正しい形を選べるか（Part 5 の標準） |
| `production` | 与えられた語を適切な形に変えて入れる |
| `processing_speed` | 平易だが即答が要る |

## 制約

- 空所は1つだけ。2箇所空けない。
- 正解が2つ成立する文にしない（曖昧なら文脈を足して1つに絞る）。
- **前置詞・イディオムを選ばせる問題（regardless of / in spite of / because of 等）では、
  空所の直後にすでに`of`等の語が続いていないか必ず確認する。**続いている場合、
  「in spite of」のように誤答選択肢でも文法的に成立するイディオムができてしまうことがある
  （2026-08-11、`toeic.part5.20260810.0005`で実際に発生: 空所直後に`of`があるのに
  「in spiteは単独でofを伴わないため誤り」という不成立の解説を書いてしまった）。
  この場合、誤答を除外する理由は文法（形が作れるか）ではなく意味（文脈に合うか）で書くこと。
- 1回の生成は依頼 JSON の `count_per_kind` 件まで（1日分をまとめて出す場合は
  複数回に分けて依頼し、「1日あたりの出題」の配分目安に沿って合計30問にする）。
