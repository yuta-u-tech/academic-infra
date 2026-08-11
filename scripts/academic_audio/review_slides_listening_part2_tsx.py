"""`review_slides_listening_part2.build_slides_listening_part2()` の出力を
project.tsx へ書く。3種のScene(質問/解説/発音)だけで、シャドーイングは無い。
"""

from __future__ import annotations

from pathlib import Path

from ._review_slides_tsx_shared import render_project_tsx as _render_project_tsx


def render_project_tsx(slides: list[dict], framescript_root: Path, *, title: str = "toeic-review-part2") -> str:
    return _render_project_tsx(slides, framescript_root, _BODY, title=title)


_BODY = '''
type QuestionSlide = {
  kind: "question"
  reviewId: string
  index: number
  questionEn: string
  choices: string[]
  soundPath: string
  durationSeconds: number
  captionsEn: CaptionCue[]
  captionsJa: CaptionCue[]
}

type ExplanationSlide = {
  kind: "explanation"
  reviewId: string
  index: number
  answerLabel: string
  explanation: string
  soundPath: string
  durationSeconds: number
  captionsEn: CaptionCue[]
  captionsJa: CaptionCue[]
}

type PronunciationSlide = {
  kind: "pronunciation"
  reviewId: string
  index: number
  points: { phrase: string; note_en: string; note_ja: string }[]
  soundPath: string
  durationSeconds: number
  captionsEn: CaptionCue[]
  captionsJa: CaptionCue[]
}

type Slide = QuestionSlide | ExplanationSlide | PronunciationSlide

const QuestionScene = ({ slide, index, total }: { slide: QuestionSlide; index: number; total: number }) => (
  <FillFrame style={{ alignItems: "center", justifyContent: "center", padding: 80 }}>
    <Background index={index} total={total} />
    <div style={{ width: "100%", maxWidth: 1500 }}>
      <Motion delay={0.05} y={16}>
        <Kicker text={`TOEIC Part 2 復習 — Question ${slide.index}`} />
      </Motion>
      <Motion delay={0.14} y={22}>
        <div style={{ marginTop: 30, fontSize: 44, fontWeight: 800, color: INK, lineHeight: 1.4 }}>
          {slide.questionEn}
        </div>
      </Motion>
      <div style={{ marginTop: 48, display: "flex", flexDirection: "column", gap: 16 }}>
        {slide.choices.map((choice, i) => (
          <Motion key={choice} delay={0.24 + i * 0.08} y={18}>
            <Glass style={{ padding: "22px 30px", display: "flex", gap: 18 }}>
              <span style={{ fontSize: 32, fontWeight: 800, color: ACCENT }}>{"ABC"[i]}.</span>
              <span style={{ fontSize: 30, fontWeight: 700, color: INK }}>{choice}</span>
            </Glass>
          </Motion>
        ))}
      </div>
    </div>
    <Sound sound={slide.soundPath} />
    <DualCaptions en={slide.captionsEn} ja={slide.captionsJa} />
  </FillFrame>
)

const ExplanationScene = ({ slide, index, total }: { slide: ExplanationSlide; index: number; total: number }) => (
  <FillFrame style={{ alignItems: "center", justifyContent: "center", padding: 80 }}>
    <Background index={index} total={total} />
    <div style={{ width: "100%", maxWidth: 1500 }}>
      <Motion delay={0.05} y={16}>
        <Kicker text="Answer" />
      </Motion>
      <Motion delay={0.12} y={20}>
        <div style={{ marginTop: 22, fontSize: 56, fontWeight: 900, color: ACCENT, letterSpacing: -1 }}>
          {slide.answerLabel}
        </div>
      </Motion>
      <Motion delay={0.24} y={18}>
        <Glass style={{ marginTop: 26, padding: "26px 32px" }}>
          <div style={{ fontSize: 26, lineHeight: 1.55, color: INK, fontWeight: 600 }}>{slide.explanation}</div>
        </Glass>
      </Motion>
    </div>
    <Sound sound={slide.soundPath} />
    <DualCaptions en={slide.captionsEn} ja={slide.captionsJa} />
  </FillFrame>
)

const PronunciationScene = ({ slide, index, total }: { slide: PronunciationSlide; index: number; total: number }) => (
  <FillFrame style={{ alignItems: "center", justifyContent: "center", padding: 80 }}>
    <Background index={index} total={total} />
    <div style={{ width: "100%", maxWidth: 1500, display: "flex", flexDirection: "column", gap: 20 }}>
      <Motion delay={0.05} y={16}>
        <Kicker text="発音のポイント" />
      </Motion>
      {slide.points.length === 0 ? (
        <Motion delay={0.16} y={18}>
          <Glass style={{ padding: "26px 32px" }}>
            <div style={{ fontSize: 26, color: MUTED }}>この設問に特筆すべき発音の難所はありません。</div>
          </Glass>
        </Motion>
      ) : (
        slide.points.map((point, i) => (
          <Motion key={point.phrase + i} delay={0.16 + i * 0.12} y={18}>
            <Glass style={{ padding: "26px 32px" }}>
              <div style={{ fontSize: 32, fontWeight: 900, color: ACCENT, marginBottom: 10 }}>{point.phrase}</div>
              <div style={{ fontSize: 22, color: INK, lineHeight: 1.5 }}>{point.note_ja}</div>
            </Glass>
          </Motion>
        ))
      )}
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
          <QuestionScene slide={slide} index={index} total={SLIDES.length} />
        ) : slide.kind === "explanation" ? (
          <ExplanationScene slide={slide} index={index} total={SLIDES.length} />
        ) : (
          <PronunciationScene slide={slide} index={index} total={SLIDES.length} />
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
