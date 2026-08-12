"""`review_slides_listening.build_slides_listening()` の出力を project.tsx へ書く。

Part5(review_slides_tsx.py)とはScene構成が違う(質問/解説/発音/シャドーイングの
4種)ので別ファイルにするが、土台(配色・Motion/Glass/Background/DualCaptions)は
`_review_slides_tsx_shared.py` を共有する。

2026-08-12: 独自に「上寄せ+下部に大きい余白」というレイアウトを考えたが、
4択の質問スライドが画面下端からはみ出して見切れた。承認済みのPart5
(review_slides_tsx.py の QuestionScene)を見直すと、はみ出さない理由は単純で、
選択肢を1列に積まず「2x2グリッド」で並べて縦の高さを半分にした上で、
`justifyContent: "center"` + 均等パディング(80px)にしているだけだった。
その実物のレイアウトをそのまま踏襲する(独自の安全マージン計算はしない)。
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
  points: { label: string; text: string }[]
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

// Part5のQuestionScene/AnswerSceneと同じ土台(center + 均等padding: 80)。
// 実測(2026-08-12): 解説スライドは構造化ポイント(2〜3枚)+文分割済みの
// 長めの字幕(英日2段)が同時に乗るため、Part5と同じpadding: 80均等では
// 字幕帯と実際に重なった(スクリーンショットで確認)。centerは維持しつつ、
// 下だけ字幕2段ぶんの高さを確保する。
const SlideFrame = ({
  index, total, children,
}: { index: number; total: number; children: React.ReactNode }) => (
  <FillFrame style={{ alignItems: "center", justifyContent: "center", padding: "70px 90px 250px" }}>
    <Background index={index} total={total} />
    {children}
  </FillFrame>
)

// 選択肢は1列に積まず2x2グリッドで並べる(Part5と同じ)。1列に積むと高さが
// 画面をはみ出す(2026-08-12に実際に見切れた)。
const QuestionScene = ({ slide, index, total }: { slide: QuestionSlide; index: number; total: number }) => (
  <SlideFrame index={index} total={total}>
    <div style={{ width: "100%", maxWidth: 1500 }}>
      <Motion delay={0.05} y={16}>
        <Kicker
          text={`TOEIC ${partLabel(slide.passageId)} 復習 — Passage ${slide.index} / Q${slide.questionNumber} of ${slide.totalQuestions}`}
        />
      </Motion>
      <Motion delay={0.14} y={22}>
        <div style={{ marginTop: 30, fontSize: 34, fontWeight: 800, color: INK, lineHeight: 1.35 }}>
          {slide.question}
        </div>
      </Motion>
      <div style={{ marginTop: 40, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {slide.choices.map((choice, i) => (
          <Motion key={choice} delay={0.22 + i * 0.06} y={18}>
            <Glass style={{ padding: "18px 22px", display: "flex", gap: 14 }}>
              <span style={{ fontSize: 22, fontWeight: 800, color: ACCENT }}>{"ABCD"[i]}.</span>
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
// Part5のAnswerPointと同じ構造化された短い要点を並べる(正解の理由だけでなく
// 他の選択肢がなぜ違うかも含める)。全文の解説そのものは下の字幕(文単位に分割済み)。
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
    <div style={{ width: "100%", maxWidth: 1500 }}>
      <Motion delay={0.05} y={16}>
        <Kicker text={`解説 — Q${slide.questionNumber} of ${slide.totalQuestions}`} />
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
        <Glass style={{ marginTop: 22, padding: "24px 30px", display: "flex", flexDirection: "column", gap: 12 }}>
          {slide.transcript.map((line, i) => (
            <div
              key={i}
              style={{
                display: "flex", gap: 14, fontSize: 21, lineHeight: 1.4,
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
