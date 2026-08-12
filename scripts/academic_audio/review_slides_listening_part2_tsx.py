"""`review_slides_listening_part2.build_slides_listening_part2()` の出力を
project.tsx へ書く。3種のScene(質問/解説/発音)だけで、シャドーイングは無い。

2026-08-12: 中央寄せレイアウトだと選択肢や解説が下端の字幕帯と重なって見えた
(プロトタイプ視聴後の指摘)。上寄せ(flex-start)にして下に十分な余白を残す。
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

// 字幕帯(DualCaptions)は画面下部に重なって表示されるため、本文は上寄せにして
// 下に十分な余白を残す(2026-08-12: 中央寄せだと選択肢が字幕と重なった)。
const SlideFrame = ({
  index, total, children,
}: { index: number; total: number; children: React.ReactNode }) => (
  <FillFrame style={{ alignItems: "center", justifyContent: "flex-start", padding: "150px 100px 320px" }}>
    <Background index={index} total={total} />
    {children}
  </FillFrame>
)

const QuestionScene = ({ slide, index, total }: { slide: QuestionSlide; index: number; total: number }) => (
  <SlideFrame index={index} total={total}>
    <div style={{ width: "100%", maxWidth: 1450 }}>
      <Motion delay={0.05} y={16}>
        <Kicker text={`TOEIC Part 2 復習 — Question ${slide.index}`} />
      </Motion>
      <Motion delay={0.14} y={22}>
        <div style={{ marginTop: 28, fontSize: 40, fontWeight: 800, color: INK, lineHeight: 1.4 }}>
          {slide.questionEn}
        </div>
      </Motion>
      <div style={{ marginTop: 42, display: "flex", flexDirection: "column", gap: 14 }}>
        {slide.choices.map((choice, i) => (
          <Motion key={choice} delay={0.24 + i * 0.08} y={18}>
            <Glass style={{ padding: "18px 26px", display: "flex", gap: 16 }}>
              <span style={{ fontSize: 28, fontWeight: 800, color: ACCENT }}>{"ABC"[i]}.</span>
              <span style={{ fontSize: 26, fontWeight: 700, color: INK }}>{choice}</span>
            </Glass>
          </Motion>
        ))}
      </div>
    </div>
    <Sound sound={slide.soundPath} />
    <DualCaptions en={slide.captionsEn} ja={slide.captionsJa} />
  </SlideFrame>
)

// 解説の全文はここには置かない。長い解説を1枚に載せると必ずはみ出す
// (2026-08-12の指摘)ので、詳細は下の字幕(文単位に分割済み)に任せる。
const ExplanationScene = ({ slide, index, total }: { slide: ExplanationSlide; index: number; total: number }) => (
  <SlideFrame index={index} total={total}>
    <div style={{ width: "100%", maxWidth: 1450 }}>
      <Motion delay={0.05} y={16}>
        <Kicker text="Answer" />
      </Motion>
      <Motion delay={0.14} y={20}>
        <div style={{ marginTop: 24, fontSize: 88, fontWeight: 900, color: ACCENT, letterSpacing: -1 }}>
          {slide.answerLabel}
        </div>
      </Motion>
    </div>
    <Sound sound={slide.soundPath} />
    <DualCaptions en={slide.captionsEn} ja={slide.captionsJa} />
  </SlideFrame>
)

const PronunciationScene = ({ slide, index, total }: { slide: PronunciationSlide; index: number; total: number }) => (
  <SlideFrame index={index} total={total}>
    <div style={{ width: "100%", maxWidth: 1450, display: "flex", flexDirection: "column", gap: 16 }}>
      <Motion delay={0.05} y={16}>
        <Kicker text="発音のポイント" />
      </Motion>
      {slide.points.length === 0 ? (
        <Motion delay={0.16} y={18}>
          <Glass style={{ padding: "24px 30px" }}>
            <div style={{ fontSize: 24, color: MUTED }}>この設問に特筆すべき発音の難所はありません。</div>
          </Glass>
        </Motion>
      ) : (
        slide.points.map((point, i) => (
          <Motion key={point.phrase + i} delay={0.16 + i * 0.12} y={18}>
            <Glass style={{ padding: "22px 30px" }}>
              <div style={{ fontSize: 28, fontWeight: 900, color: ACCENT, marginBottom: 8 }}>{point.phrase}</div>
              <div style={{ fontSize: 20, color: INK, lineHeight: 1.5 }}>{point.note_ja}</div>
            </Glass>
          </Motion>
        ))
      )}
    </div>
    <Sound sound={slide.soundPath} />
    <DualCaptions en={slide.captionsEn} ja={slide.captionsJa} />
  </SlideFrame>
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
