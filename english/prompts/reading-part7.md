# 読解問題（TOEIC Part7 相当）の生成（prompt_version: 2026-08-05.1）

**TOEIC Part 7 と同じ形**の読解問題を作る。Part 5（`grammar.md`）と違い、素材（VOA/TED等）の
語彙・場面を借りる必要はない — Part7のパッセージ自体がオリジナルの読み物になる。
市販の問題集から問題文・パッセージを写さない。ビジネス文書（メール・通知・広告・記事・
チャット等）を、TOEICで実際に出る形式に沿ってこちらで作る。

## 出力するJSONの構造

`grammar.md`（Part5）とは形が異なる。トップレベルは以下（`toeic_reading_cli.py worksheet-part7`/
`ingest-part7` がこの形をそのまま読む。生成結果はDB保存時に内部で `ReadingItem` へ変換されるが、
ここで書くJSONはその変換前の「パッセージごとにまとめた」形）:

```json
{
  "title": "Part7 <YYYY-MM-DD>",
  "passages": [
    {
      "passage": "本文（single/double/tripleいずれも1つの文字列。複数文書の場合は\n\n で区切る）",
      "passage_type": "single",
      "questions": [
        {
          "question": "...",
          "choices": ["...", "...", "...", "..."],
          "answer_index": 0,
          "explanation": "...",
          "sub_skill": "comprehension"
        }
      ]
    }
  ]
}
```

## 難易度の目標（900点、990点ではない）

TOEIC900点はPart7全問を時間内に解き切れる帯にあたる。この帯で外してはいけないのは
**「本文の1文をそのまま探せば答えが見つかる問題（600点レベル）ばかりにしない」**という点。
言い換え・要約・推論（本文に明示されていないが論理的に導ける内容）を問う設問を、
900点向けセットでは半分以上入れる。

## passage_type とパッセージの作り方

| 値 | 構成 | 設問数の目安 |
|---|---|---|
| `single` | 文書1つ（メール・通知・広告・記事など） | 2〜4問 |
| `double` | 関連する文書2つ（例: メールとその返信、広告と問い合わせメール） | 5問 |
| `triple` | 関連する文書3つ（例: 広告・注文確認・苦情メール） | 5問 |

- `double`/`triple` では、**設問の少なくとも1つを複数文書をまたがないと解けない設計にする**
  （例: 文書1の日付と文書2の金額を照合させる）。これがPart7で最も差がつく設問形式。
- 場面はビジネス文脈（社内連絡・注文/出荷・人事・出張・イベント案内）を優先する。
  TOEICの出題場面がそこに偏るため。
- 1パッセージは200〜400語程度（`single`はやや短め、`double`/`triple`は文書ごとに100〜200語）。

## question / choices / answer_index

- 4択が基本（3〜5択まで可）。`answer_index` は0始まり。
- 設問の種類を1パッセージ内で偏らせない。目安:
  - **主題・目的**（"What is the purpose of this email?"）
  - **詳細検索**（"According to the notice, when will..."）
  - **NOT問題**（"What is NOT mentioned as..."）
  - **推論**（"What can be inferred about..."、本文に明示されない内容を論理的に導く）
  - **語彙**（"The word 'X' in paragraph 2 is closest in meaning to"）
  - **文脈挿入**（"In what position marked [1], [2], [3], [4] does the following sentence best belong?"、
    シングルパッセージの長文で使う）
- 正解が2つ成立する設問にしない（曖昧なら本文側に情報を足して1つに絞る）。
- 誤答は「本文に出てくるが問われている箇所とは無関係な情報」「本文の内容を歪曲した記述」
  「本文に書かれていない推測」など、**本文を読んでいないと除外できない**選択肢にする
  （パッセージを読まずに常識だけで消去できる誤答は作らない）。

## explanation

正解の根拠になる本文箇所を示した上で、**誤答がなぜ不正解かも1つずつ触れる**
（「本文のどこにも書かれていない」「本文と矛盾する」など）。長くなりすぎないよう
誤答1つにつき1文程度（`explanation` 全体で2000字以内）。

## sub_skill

`items.py` の `READING_SUB_SKILLS` と同じ4値を使う:

| 値 | どういう問題か |
|---|---|
| `comprehension` | 本文の内容理解（主題・詳細・NOT問題） |
| `syntax_parsing` | 文脈挿入など、構文・論理構造の把握が要る |
| `vocabulary` | 語彙の言い換え問題 |
| `reading_speed` | 平易だが時間内に読み切る速度が要る（`double`/`triple`の照合問題など） |

## 制約

- 1回の生成は依頼された件数（パッセージ数）まで。パッセージ数・構成比（single多め、
  double/tripleは週に数セット程度）はユーザー指定が無ければ「single 3〜4・double 1・
  triple 1」程度を目安にする。
- 同じ場面・登場人物・企業名を使い回しすぎない（`grammar.md`の使用済み語彙ログと同様、
  マンネリを避ける）。
