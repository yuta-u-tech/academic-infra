# 長文穴埋め問題（TOEIC Part6 相当）の生成（prompt_version: 2026-08-14.1）

**TOEIC Part 6 と同じ形**の長文穴埋め問題を作る。Part5（`grammar.md`）の「1文=1空所」を
「1passage=4空所」に拡張したもの。市販の問題集からパッセージ・問題文を写さない。

## 出力するJSONの構造

トップレベルは `toeic_reading_cli.py worksheet-part6`/`shuffle-part6`/`ingest-part6` が
そのまま読む形（Part7の`reading-part7.md`と同じpassagesグルーピングだが、questionsの
中身がPart5のGrammarItemに近い）:

```json
{
  "title": "Part6 <YYYY-MM-DD>",
  "passages": [
    {
      "passage": "本文。空所は [1]〜[4] で示す（____ ではない。Part5と記法を変えているのは、
        1passageに4箇所あるため番号で区別する必要があるため）。",
      "passage_type": "email",
      "questions": [
        {
          "blank_number": 1,
          "blank_type": "word",
          "choices": ["...", "...", "...", "..."],
          "answer_index": 0,
          "explanation": "...",
          "point": "...",
          "pattern": "A",
          "pattern_note": "..."
        }
      ]
    }
  ]
}
```

- `passage_type`: `email` / `memo` / `notice` / `advertisement` / `article` のいずれか。
- `questions`は`blank_number`の1〜4を**必ず全て含む**（4問ちょうど）。
- **[1]〜[3]は`blank_type: "word"`（Part5と同じ単語/句選択、`pattern`(A/B/C)/`pattern_note`必須）、
  [4]は`blank_type: "sentence"`（4つの文から文脈に最も合うものを選ぶ、Part6特有の設問。
  `pattern`/`pattern_note`は省略可）**——どの番号を文挿入にするかは固定せず、パッセージごとに
  自然な位置（段落の切れ目等）に配置してよいが、**1passageにつき文挿入は必ず1問だけ**。

## word型の空所（choices/answer_index/point/pattern/pattern_note）

`grammar.md`の「choices / answer_index」「point / pattern / pattern_note」節と同じ基準
（パターンA=同じ語の別の形、B=似ているが別の語、C=コロケーション知識）。Part6は文書全体の
文脈（前後の文・段落）を読まないと絞れない設計にする——Part5と違い1文だけでは解けない
問題を混ぜてよい（むしろそれがPart6らしさ）。

## sentence型の空所（[4]、choices/answer_index）

- 4択の文から、直前・直後の文脈と整合する1文を選ばせる。誤答は「文法的には正しい英文だが、
  話の流れ・時制・話題に合わない」ものにする（全く無関係な文だと消去法で解けてしまう）。
- `explanation`には、なぜ正解が流れに合うか、誤答がなぜ話の流れに合わないかを書く。

## passage

- 200〜250語程度のビジネス文書（社内連絡・注文確認・イベント案内・製品案内・お知らせ等）。
- 1passageに1つの話題。段落は2〜4個程度に分ける。

## explanation / point

`grammar.md`と同じ基準（誤答ごとに正しい使われ方を示す。`point`は「副詞と形容詞の区別」
のように具体的に書く）。

## 1日あたりの出題

既定は「4 passage × 4問 = 16問」。Part5と同じく通常＋苦手重点の2段構成を想定するが、
`toeic_reading_cli.py weak-points-part6`の誤答データが少ないうちは全passage通常配分でよい
（無理に苦手重点を捏造しない）。データが溜まってきたら1passageを苦手重点に差し替える。

書いた直後、`worksheet-part6`/`ingest-part6`/Form作成のいずれよりも前に、必ず
`toeic_reading_cli.py shuffle-part6 --items items.json` を実行すること（passage順序・
選択肢順序を機械的にシャッフルする。review_idはシャッフル後の順で決まる）。
