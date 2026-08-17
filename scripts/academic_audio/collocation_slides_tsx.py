"""`collocation_slides.build_slides()` が作ったスライド配列を、FrameScriptの
project.tsxへ書く。

デザイン(Glass/Background/Motion・配色)は `_review_slides_tsx_shared.py` を再利用。
コロケーションのバッジ表示は review_slides_tsx.py の AnswerPoint と同じく
崩れない可変幅ピル(2026-08-18の教訓)にしてある。
"""

from __future__ import annotations

from pathlib import Path

from ._review_slides_tsx_shared import render_project_tsx as _render_project_tsx


def render_project_tsx(
    slides: list[dict],
    framescript_root: Path,
    *,
    title: str = "toeic-collocation",
    page_offset: int = 0,
    page_total: int | None = None,
) -> str:
    return _render_project_tsx(
        slides, framescript_root, _BODY, title=title, page_offset=page_offset, page_total=page_total
    )


_BODY = '''
type CollocationSlide = {
  kind: "collocation"
  reviewId: string
  word: string
  meaning: string
  partOfSpeech: string | null
  collocations: string[]
  collocationsJa: string[]
  exampleEn: string
  exampleJa: string
  soundPath: string
  durationSeconds: number
  captionsEn: CaptionCue[]
  captionsJa: CaptionCue[]
}

type Slide = CollocationSlide

const CollocationChip = ({ text, textJa, delay }: { text: string; textJa: string; delay: number }) => (
  <Motion delay={delay} y={14}>
    <Glass
      style={{
        padding: "14px 22px", display: "inline-flex", flexDirection: "column", gap: 4,
        borderRadius: 18, background: ACCENT_SOFT, border: "none", boxShadow: "none",
      }}
    >
      <span style={{ fontSize: 28, fontWeight: 700, color: ACCENT, whiteSpace: "nowrap" }}>{text}</span>
      <span style={{ fontSize: 18, fontWeight: 600, color: MUTED, whiteSpace: "nowrap" }}>{textJa}</span>
    </Glass>
  </Motion>
)

const CollocationScene = ({ slide, index, total }: { slide: CollocationSlide; index: number; total: number }) => (
  <FillFrame style={{ alignItems: "center", justifyContent: "center", padding: 80 }}>
    <Background index={index} total={total} />
    <div style={{ width: "100%", maxWidth: 1560 }}>
      <Motion delay={0.05} y={16}>
        <Kicker text="Collocation" />
      </Motion>
      <Motion delay={0.12} y={20}>
        <div style={{ marginTop: 22, display: "flex", alignItems: "baseline", gap: 20 }}>
          <div style={{ fontSize: 72, fontWeight: 900, color: INK, letterSpacing: -1 }}>{slide.word}</div>
          {slide.partOfSpeech ? (
            <div style={{ fontSize: 24, fontWeight: 700, color: MUTED }}>{slide.partOfSpeech}</div>
          ) : null}
          <div style={{ fontSize: 32, fontWeight: 700, color: ACCENT }}>{slide.meaning}</div>
        </div>
      </Motion>
      <div style={{ marginTop: 34, display: "flex", flexWrap: "wrap", gap: 14 }}>
        {slide.collocations.map((text, i) => (
          <CollocationChip key={text + i} text={text} textJa={slide.collocationsJa[i]} delay={0.24 + i * 0.1} />
        ))}
      </div>
      <Motion delay={0.24 + slide.collocations.length * 0.1 + 0.12} y={12}>
        <Glass style={{ marginTop: 34, padding: "22px 28px" }}>
          <div style={{ fontSize: 26, lineHeight: 1.5, color: INK, fontWeight: 600 }}>{slide.exampleEn}</div>
          <div style={{ marginTop: 8, fontSize: 20, lineHeight: 1.5, color: MUTED }}>{slide.exampleJa}</div>
        </Glass>
      </Motion>
    </div>
    <Sound sound={slide.soundPath} />
    <DualCaptions en={slide.captionsEn} ja={slide.captionsJa} />
  </FillFrame>
)

const VisualTrack = () => (
  <ClipSequence>
    {SLIDES.map((slide, index) => (
      <Clip key={`${slide.reviewId}-${slide.kind}`} label={`${slide.reviewId}-${slide.kind}`} duration={seconds(slide.durationSeconds)}>
        <CollocationScene slide={slide} index={PAGE_OFFSET + index} total={PAGE_TOTAL} />
      </Clip>
    ))}
  </ClipSequence>
)

export const PROJECT = () => {
  return (
    <Project>
      <TimeLine>
        <VisualTrack />
      </TimeLine>
    </Project>
  )
}
'''
