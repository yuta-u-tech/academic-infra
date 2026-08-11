"""`review_slides_listening.build_slides_listening()` の出力を project.tsx へ書く。

Part5(review_slides_tsx.py)とはScene構成が違う(質問/解説/発音/シャドーイングの
4種)ので別ファイルにするが、土台(配色・Motion/Glass/Background/DualCaptions)は
`_review_slides_tsx_shared.py` を共有する。
"""

from __future__ import annotations

from pathlib import Path

from ._review_slides_tsx_shared import render_project_tsx as _render_project_tsx


def render_project_tsx(slides: list[dict], framescript_root: Path, *, title: str = "toeic-review-listening") -> str:
    return _render_project_tsx(slides, framescript_root, _BODY, title=title)


_BODY = '''
type QuestionSlide = {
  kind: "question"
  passageId: string
  index: number
  questions: { question: string; choices: string[]; reviewId: string }[]
  soundPath: string
  durationSeconds: number
  captionsEn: CaptionCue[]
  captionsJa: CaptionCue[]
}

type ExplanationSlide = {
  kind: "explanation"
  passageId: string
  index: number
  questions: { answerLabel: string; explanation: string }[]
  soundPath: string
  durationSeconds: number
  captionsEn: CaptionCue[]
  captionsJa: CaptionCue[]
}

type PronunciationSlide = {
  kind: "pronunciation"
  passageId: string
  index: number
  points: { phrase: string; note_en: string; note_ja: string }[]
  soundPath: string
  durationSeconds: number
  captionsEn: CaptionCue[]
  captionsJa: CaptionCue[]
}

type ShadowingSlide = {
  kind: "shadowing"
  passageId: string
  index: number
  transcript: { speaker: string; text: string }[]
  soundPath: string
  durationSeconds: number
  captionsEn: CaptionCue[]
  captionsJa: CaptionCue[]
}

type Slide = QuestionSlide | ExplanationSlide | PronunciationSlide | ShadowingSlide

const partLabel = (passageId: string) => (passageId.includes(".part4.") ? "Part 4" : "Part 3")

const QuestionScene = ({ slide, index, total }: { slide: QuestionSlide; index: number; total: number }) => (
  <FillFrame style={{ alignItems: "center", justifyContent: "center", padding: 80 }}>
    <Background index={index} total={total} />
    <div style={{ width: "100%", maxWidth: 1560, display: "flex", flexDirection: "column", gap: 22 }}>
      <Motion delay={0.05} y={16}>
        <Kicker text={`TOEIC ${partLabel(slide.passageId)} 復習 — Passage ${slide.index}`} />
      </Motion>
      {slide.questions.map((question, i) => (
        <Motion key={question.reviewId} delay={0.14 + i * 0.1} y={20}>
          <Glass style={{ padding: "22px 30px" }}>
            <div style={{ fontSize: 30, fontWeight: 800, color: INK, marginBottom: 14 }}>
              {i + 1}. {question.question}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              {question.choices.map((choice, j) => (
                <div key={choice} style={{ fontSize: 22, color: MUTED, display: "flex", gap: 10 }}>
                  <span style={{ fontWeight: 800, color: ACCENT }}>{"ABCD"[j]}.</span>
                  <span>{choice}</span>
                </div>
              ))}
            </div>
          </Glass>
        </Motion>
      ))}
    </div>
    <Sound sound={slide.soundPath} />
    <DualCaptions en={slide.captionsEn} ja={slide.captionsJa} />
  </FillFrame>
)

const ExplanationScene = ({ slide, index, total }: { slide: ExplanationSlide; index: number; total: number }) => (
  <FillFrame style={{ alignItems: "center", justifyContent: "center", padding: 80 }}>
    <Background index={index} total={total} />
    <div style={{ width: "100%", maxWidth: 1560, display: "flex", flexDirection: "column", gap: 20 }}>
      <Motion delay={0.05} y={16}>
        <Kicker text="解説" />
      </Motion>
      {slide.questions.map((question, i) => (
        <Motion key={i} delay={0.14 + i * 0.1} y={20}>
          <Glass style={{ padding: "22px 30px", display: "flex", gap: 18, alignItems: "flex-start" }}>
            <div
              style={{
                flexShrink: 0, width: 46, height: 46, borderRadius: 999, background: ACCENT_SOFT, color: ACCENT,
                fontSize: 22, fontWeight: 900, display: "flex", alignItems: "center", justifyContent: "center",
              }}
            >
              {question.answerLabel}
            </div>
            <div style={{ fontSize: 24, lineHeight: 1.55, color: INK, fontWeight: 600 }}>{question.explanation}</div>
          </Glass>
        </Motion>
      ))}
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
            <div style={{ fontSize: 26, color: MUTED }}>このパッセージに特筆すべき発音の難所はありません。</div>
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

const ShadowingScene = ({ slide, index, total }: { slide: ShadowingSlide; index: number; total: number }) => {
  const frame = useCurrentFrame()
  const t = PROJECT_SETTINGS.fps > 0 ? frame / PROJECT_SETTINGS.fps : 0
  const activeLine = slide.captionsEn.findIndex((cue) => t >= cue.start && t < cue.end)
  return (
    <FillFrame style={{ alignItems: "center", justifyContent: "center", padding: 80 }}>
      <Background index={index} total={total} />
      <div style={{ width: "100%", maxWidth: 1400 }}>
        <Motion delay={0.05} y={16}>
          <Kicker text="シャドーイング" />
        </Motion>
        <Glass style={{ marginTop: 24, padding: "34px 40px", display: "flex", flexDirection: "column", gap: 18 }}>
          {slide.transcript.map((line, i) => (
            <div
              key={i}
              style={{
                display: "flex", gap: 16, fontSize: 28, lineHeight: 1.5,
                color: i === activeLine ? INK : MUTED,
                fontWeight: i === activeLine ? 800 : 600,
                opacity: i === activeLine ? 1 : 0.55,
              }}
            >
              <span style={{ flexShrink: 0, fontWeight: 900, color: ACCENT }}>{line.speaker}:</span>
              <span>{line.text}</span>
            </div>
          ))}
        </Glass>
      </div>
      <Sound sound={slide.soundPath} />
    </FillFrame>
  )
}

const VisualTrack = () => (
  <ClipSequence>
    {SLIDES.map((slide, index) => (
      <Clip key={`${slide.passageId}-${slide.kind}`} label={`${slide.passageId}-${slide.kind}`} duration={seconds(slide.durationSeconds)}>
        {slide.kind === "question" ? (
          <QuestionScene slide={slide} index={index} total={SLIDES.length} />
        ) : slide.kind === "explanation" ? (
          <ExplanationScene slide={slide} index={index} total={SLIDES.length} />
        ) : slide.kind === "pronunciation" ? (
          <PronunciationScene slide={slide} index={index} total={SLIDES.length} />
        ) : (
          <ShadowingScene slide={slide} index={index} total={SLIDES.length} />
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
