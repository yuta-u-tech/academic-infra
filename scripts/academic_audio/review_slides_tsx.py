"""`review_slides.build_slides()` が作ったスライド配列を、FrameScriptのproject.tsxへ書く。

デザイン(Glass/Background/Motion・配色)は `~/FrameScript-toeic-review` で試作して
ユーザー承認済みのものを `_review_slides_tsx_shared.py` に切り出してある。ここには
Part5固有のScene(QuestionScene/AnswerScene)だけを持つ。
"""

from __future__ import annotations

from pathlib import Path

from ._review_slides_tsx_shared import render_project_tsx as _render_project_tsx

CHANNEL_LABEL = "TOEIC 復習"


def render_project_tsx(
    slides: list[dict],
    framescript_root: Path,
    *,
    title: str = "toeic-review",
    page_offset: int = 0,
    page_total: int | None = None,
) -> str:
    return _render_project_tsx(
        slides, framescript_root, _BODY, title=title, page_offset=page_offset, page_total=page_total
    )


_BODY = '''
type QuestionSlide = {
  kind: "question"
  reviewId: string
  index: number
  sentence: string
  choices: string[]
  soundPath: string
  durationSeconds: number
  captionsEn: CaptionCue[]
  captionsJa: CaptionCue[]
}

type AnswerSlide = {
  kind: "answer"
  reviewId: string
  answerLabel: string
  answerWord: string
  points: { label: string; text: string }[]
  example: string
  soundPath: string
  durationSeconds: number
  captionsEn: CaptionCue[]
  captionsJa: CaptionCue[]
}

type Slide = QuestionSlide | AnswerSlide

const QuestionScene = ({ slide, index, total }: { slide: QuestionSlide; index: number; total: number }) => (
  <FillFrame style={{ alignItems: "center", justifyContent: "center", padding: 80 }}>
    <Background index={index} total={total} />
    <div style={{ width: "100%", maxWidth: 1500 }}>
      <Motion delay={0.05} y={16}>
        <Kicker text={`TOEIC Part 5 復習 — Question ${slide.index}`} />
      </Motion>
      <Motion delay={0.14} y={22}>
        <div
          style={{
            marginTop: 30, fontSize: 48, fontWeight: 800, color: INK, lineHeight: 1.35, letterSpacing: -0.5,
            fontFamily: '"Hiragino Sans", "Yu Gothic", sans-serif',
          }}
        >
          {slide.sentence.split("____")[0]}
          <span style={{ color: ACCENT }}>____</span>
          {slide.sentence.split("____")[1]}
        </div>
      </Motion>
      <div style={{ marginTop: 56, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
        {slide.choices.map((choice, i) => (
          <Motion key={choice} delay={0.22 + i * 0.06} y={18}>
            <Glass style={{ padding: "24px 32px", display: "flex", gap: 18 }}>
              <span style={{ fontSize: 36, fontWeight: 800, color: ACCENT }}>{"ABCD"[i]}.</span>
              <span style={{ fontSize: 36, fontWeight: 700, color: INK }}>{choice}</span>
            </Glass>
          </Motion>
        ))}
      </div>
    </div>
    <Sound sound={slide.soundPath} />
    <DualCaptions en={slide.captionsEn} ja={slide.captionsJa} />
  </FillFrame>
)

const AnswerPoint = ({ label, text, delay }: { label: string; text: string; delay: number }) => (
  <Motion delay={delay} y={16}>
    <Glass style={{ padding: "20px 26px", display: "flex", gap: 18, alignItems: "flex-start" }}>
      <div
        style={{
          flexShrink: 0, minWidth: 40, padding: "8px 14px", borderRadius: 999, background: ACCENT_SOFT, color: ACCENT,
          fontSize: 16, fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center",
          whiteSpace: "nowrap", lineHeight: 1.2,
        }}
      >
        {label}
      </div>
      <div style={{ fontSize: 26, lineHeight: 1.45, color: INK, fontWeight: 600, flex: 1, minWidth: 0 }}>{text}</div>
    </Glass>
  </Motion>
)

const AnswerScene = ({ slide, index, total }: { slide: AnswerSlide; index: number; total: number }) => (
  <FillFrame style={{ alignItems: "center", justifyContent: "center", padding: 80 }}>
    <Background index={index} total={total} />
    <div style={{ width: "100%", maxWidth: 1560 }}>
      <Motion delay={0.05} y={16}>
        <Kicker text="Answer" />
      </Motion>
      <Motion delay={0.12} y={20}>
        <div style={{ marginTop: 22, fontSize: 56, fontWeight: 900, color: ACCENT, letterSpacing: -1 }}>
          {slide.answerLabel}. {slide.answerWord}
        </div>
      </Motion>
      <div style={{ marginTop: 26, display: "flex", flexDirection: "column", gap: 16 }}>
        {slide.points.map((point, i) => (
          <AnswerPoint key={point.label + i} delay={0.22 + i * 0.08} label={point.label} text={point.text} />
        ))}
      </div>
      {slide.example ? (
        <Motion delay={0.22 + slide.points.length * 0.08 + 0.1} y={12}>
          <div style={{ marginTop: 26, fontSize: 22, color: MUTED }}>例: {slide.example}</div>
        </Motion>
      ) : null}
    </div>
    <Sound sound={slide.soundPath} />
    <DualCaptions en={slide.captionsEn} ja={slide.captionsJa} />
  </FillFrame>
)

const VisualTrack = () => (
  <ClipSequence>
    {SLIDES.map((slide, index) => (
      <Clip key={`${slide.reviewId}-${slide.kind}`} label={`${slide.reviewId}-${slide.kind}`} duration={seconds(slide.durationSeconds)}>
        {slide.kind === "question" ? (
          <QuestionScene slide={slide} index={PAGE_OFFSET + index} total={PAGE_TOTAL} />
        ) : (
          <AnswerScene slide={slide} index={PAGE_OFFSET + index} total={PAGE_TOTAL} />
        )}
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
