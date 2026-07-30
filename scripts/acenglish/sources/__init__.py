"""外部素材（科目資料以外）の取り込み。

科目資料は `target.py` が `courses.yml` + `review-manifest.json` から解決するが、
一般英語・TOEIC の素材は academic-infra の中に存在しない。ここはその穴を埋める層で、
どの取得元も最終的に `ExternalMaterial` に正規化され、以降は科目資料とまったく同じ
生成・学習・誤答分析の経路に乗る。

    studyforge  study-forge の TOEIC 語彙デッキ（既に語義・例文があるので生成不要）
    voa         VOA Learning English（米国政府著作物＝パブリックドメイン）
    ted         TED / YouTube の字幕（yt-dlp）

**還元先が科目資料と違う。** 外部素材には「直すべき章」が無いので、誤答が反復したときの
追記候補は科目リポジトリではなく `~/english-notes` の drafts/ へ向かう（`notes.py`）。
"""

from .base import ExternalMaterial, note_path_for, slugify

__all__ = ["ExternalMaterial", "note_path_for", "slugify"]
