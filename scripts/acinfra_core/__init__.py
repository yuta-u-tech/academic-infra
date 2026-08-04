"""Goal駆動型学習オペレーション基盤の Core 層。

設計: docs/2026-08-04-goal-driven-learning-platform.md
Evidence/Mastery は Core に複製せず、Domain Plugin（例: acenglish）に残したまま
`competency.domain_ref` で緩く参照する。
"""
