---
id: toeic-part1
name: TOEIC Part 1（写真描写）
engine: piper
language: en
speakers: 1
answer_in_audio: true
grouping: flat
item:
  - role: choice
    count: 4
    words: [6, 15]
    pause: 0.5
---

# TOEIC Part 1 形式のリスニング問題

1枚の写真を見て、それを最もよく描写している文を4つの選択肢(A)(B)(C)(D)から選ぶ。
**本番同様、質問文は無い**（Part2の`question`役割が存在しない唯一の形式。`Number N.`の
通し番号読み上げの後、4つの描写文だけが読まれる）。写真は`image_path`で1問ごとに紐づく
（Codex等で生成し、`~/academic-english-data/listening/part1/<slug>/images/`に保存する。
正本はDrive/YouTubeではなくこのディレクトリ）。

`Number N.` の通し番号読み上げ・各描写文前の`A.` `B.` `C.` `D.`読み上げ・次の問題までの
マーク時間は`items.py: to_script()`が自動で付与する。作問側（Claude）は`choice`の本文
（4つの描写文）だけを書けばよい（記号は書かない）。

## 写真の題材

TOEIC本番の定番シーン（オフィス・工事現場・店舗・公園・駅・厨房・倉庫等）から選ぶ。
実在の人物・商標・読める文字（看板の文言等）が写り込まないよう画像生成プロンプトで
明示的に避ける。1人〜数人の人物が写る「人物中心」の写真と、人物が写らない「物・風景中心」
の写真の両方を混ぜる（本番でも両方出る）。

## 描写文（choice）の型

- 人物写真: 動作（現在進行形が中心）・服装・位置関係を描写する文を混ぜる。
  例: "A woman is typing on a laptop." / "Some people are seated around a table."
- 物・風景写真: 存在・状態・配置を描写する文。
  例: "Chairs have been stacked against the wall." / "A path leads through the trees."
- 誤答は「写真に写っていない動作」「似た音の別の語」「写っている物の誤認」等、本番の
  典型的な誤答パターンに沿わせる。正解は**実際に生成された画像を見た上で**、そこに
  写っているものと矛盾しないように書く（画像生成プロンプトの「意図」ではなく「実際の
  仕上がり」を根拠にする）。

## answer_index

4択中1つが正解。0始まり。
