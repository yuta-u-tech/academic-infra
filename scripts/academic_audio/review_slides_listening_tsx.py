"""`review_slides_listening.build_slides_listening()` の出力を project.tsx へ書く。

Part5(review_slides_tsx.py)とはScene構成が違う(質問/解説/発音/シャドーイングの
4種)ので別ファイルにするが、土台(配色・Motion/Glass/Background/DualCaptions)は
`_review_slides_tsx_shared.py` を共有する。

2026-08-12: 3問+選択肢を1枚に全部乗せた最初のプロトタイプは字幕と重なるほど
密度過多だった(視聴後の指摘)。1問=1枚に割った上で、レイアウトも画面中央寄せから
上寄せ(flex-start)に変え、コンテンツが下端の字幕帯に伸びていかないようにした。
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
  questionNumber: number
  totalQuestions: number
  question: string
  choices: string[]
  reviewId: string
  soundPath: string
  durationSeconds: number
  captionsEn: CaptionCue[]
  captionsJa: CaptionCue[]
}

type ExplanationSlide = {
  kind: "explanation"
  passageId: string
  index: number
  questionNumber: number
  totalQuestions: number
  answerLabel: string
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

// 字幕帯(DualCaptions)は画面下部に重なって表示されるため、本文は上寄せにして
// 下に十分な余白を残す(2026-08-12: 中央寄せだと選択肢や解説が字幕と重なった)。
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
    <div style={{ width: "100%", maxWidth: 1500 }}>
      <Motion delay={0.05} y={16}>
        <Kicker
          text={`TOEIC ${partLabel(slide.passageId)} 復習 — Passage ${slide.index} / Q${slide.questionNumber} of ${slide.totalQuestions}`}
        />
      </Motion>
      <Motion delay={0.14} y={22}>
        <div style={{ marginTop: 30, fontSize: 42, fontWeight: 800, color: INK, lineHeight: 1.4 }}>
          {slide.question}
        </div>
      </Motion>
      <div style={{ marginTop: 44, display: "flex", flexDirection: "column", gap: 14 }}>
        {slide.choices.map((choice, i) => (
          <Motion key={choice} delay={0.24 + i * 0.08} y={18}>
            <Glass style={{ padding: "18px 26px", display: "flex", gap: 16 }}>
              <span style={{ fontSize: 26, fontWeight: 800, color: ACCENT }}>{"ABCD"[i]}.</span>
              <span style={{ fontSize: 24, fontWeight: 700, color: INK }}>{choice}</span>
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
    <div style={{ width: "100%", maxWidth: 1500 }}>
      <Motion delay={0.05} y={16}>
        <Kicker text={`解説 — Q${slide.questionNumber} of ${slide.totalQuestions}`} />
      </Motion>
      <Motion delay={0.14} y={20}>
        <div style={{ marginTop: 26, fontSize: 88, fontWeight: 900, color: ACCENT, letterSpacing: -1 }}>
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
            <div style={{ fontSize: 24, color: MUTED }}>このパッセージに特筆すべき発音の難所はありません。</div>
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

const ShadowingScene = ({ slide, index, total }: { slide: ShadowingSlide; index: number; total: number }) => {
  const frame = useCurrentFrame()
  const t = PROJECT_SETTINGS.fps > 0 ? frame / PROJECT_SETTINGS.fps : 0
  const activeLine = slide.captionsEn.findIndex((cue) => t >= cue.start && t < cue.end)
  return (
    <SlideFrame index={index} total={total}>
      <div style={{ width: "100%", maxWidth: 1350 }}>
        <Motion delay={0.05} y={16}>
          <Kicker text="シャドーイング" />
        </Motion>
        <Glass style={{ marginTop: 22, padding: "26px 32px", display: "flex", flexDirection: "column", gap: 14 }}>
          {slide.transcript.map((line, i) => (
            <div
              key={i}
              style={{
                display: "flex", gap: 14, fontSize: 24, lineHeight: 1.5,
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
    </SlideFrame>
  )
}

const VisualTrack = () => (
  <ClipSequence>
    {SLIDES.map((slide, index) => (
      <Clip key={`${slide.passageId}-${slide.kind}-${index}`} label={`${slide.passageId}-${slide.kind}`} duration={seconds(slide.durationSeconds)}>
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
