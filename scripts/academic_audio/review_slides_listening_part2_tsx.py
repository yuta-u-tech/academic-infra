"""`review_slides_listening_part2.build_slides_listening_part2()` の出力を
project.tsx へ書く。3種のScene(質問/解説/発音)だけで、シャドーイングは無い。

2026-08-12: 承認済みのPart5(review_slides_tsx.py)と同じ土台
(`justifyContent: "center"` + 均等padding: 80)にする。以前は独自に
「上寄せ+下部に大きい余白」を試したが、それでも質問スライドが画面下端から
はみ出して見切れた。Part5がはみ出さないのは選択肢の総高さがそもそも小さいから
であって、寄せ方の問題ではなかった。
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
  points: { label: string; text: string }[]
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

// Part5のQuestionScene/AnswerSceneと同じ土台(center + 均等padding: 80)。
const SlideFrame = ({
  index, total, children,
}: { index: number; total: number; children: React.ReactNode }) => (
  <FillFrame style={{ alignItems: "center", justifyContent: "center", padding: 80 }}>
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
        <div style={{ marginTop: 26, fontSize: 34, fontWeight: 800, color: INK, lineHeight: 1.35 }}>
          {slide.questionEn}
        </div>
      </Motion>
      <div style={{ marginTop: 32, display: "flex", flexDirection: "column", gap: 12 }}>
        {slide.choices.map((choice, i) => (
          <Motion key={choice} delay={0.24 + i * 0.08} y={18}>
            <Glass style={{ padding: "16px 22px", display: "flex", gap: 14 }}>
              <span style={{ fontSize: 22, fontWeight: 800, color: ACCENT }}>{"ABC"[i]}.</span>
              <span style={{ fontSize: 21, fontWeight: 700, color: INK, lineHeight: 1.3 }}>{choice}</span>
            </Glass>
          </Motion>
        ))}
      </div>
    </div>
    <Sound sound={slide.soundPath} />
    <DualCaptions en={slide.captionsEn} ja={slide.captionsJa} />
  </SlideFrame>
)

// 答えの文字だけでは解説として粒度が低いという指摘(2026-08-12)への対応。
// Part5のAnswerPointと同じ構造化された短い要点を並べる。
const ExplanationPoint = ({ label, text, delay }: { label: string; text: string; delay: number }) => (
  <Motion delay={delay} y={16}>
    <Glass style={{ padding: "16px 22px", display: "flex", gap: 16, alignItems: "flex-start" }}>
      <div
        style={{
          flexShrink: 0, width: 34, height: 34, borderRadius: 999, background: ACCENT_SOFT, color: ACCENT,
          fontSize: 16, fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center",
        }}
      >
        {label}
      </div>
      <div style={{ fontSize: 20, lineHeight: 1.4, color: INK, fontWeight: 600 }}>{text}</div>
    </Glass>
  </Motion>
)

const ExplanationScene = ({ slide, index, total }: { slide: ExplanationSlide; index: number; total: number }) => (
  <SlideFrame index={index} total={total}>
    <div style={{ width: "100%", maxWidth: 1450 }}>
      <Motion delay={0.05} y={16}>
        <Kicker text="Answer" />
      </Motion>
      <Motion delay={0.12} y={20}>
        <div style={{ marginTop: 20, fontSize: 44, fontWeight: 900, color: ACCENT, letterSpacing: -1 }}>
          正解: {slide.answerLabel}
        </div>
      </Motion>
      <div style={{ marginTop: 20, display: "flex", flexDirection: "column", gap: 10 }}>
        {slide.points.map((point, i) => (
          <ExplanationPoint key={point.label + i} delay={0.2 + i * 0.08} label={point.label} text={point.text} />
        ))}
      </div>
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
