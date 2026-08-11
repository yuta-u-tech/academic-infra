"""Part5/リスニング(Part2/Part3/4)、全テンプレート共通のFrameScript土台。

配色・Motion/Glass/Background/DualCaptionsは `~/FrameScript-toeic-review` で試作して
ユーザー承認済みのもの(review_slides_tsx.pyがPart5で最初に確立した)。テンプレートが
増えるたびに丸ごとコピーすると承認済みデザインが少しずつずれていくので、ここに
1箇所だけ持つ。各テンプレートは `_BODY`(スライド種別ごとのScene)だけ自分で書く。
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def relative_sound_path(sound_path: str, framescript_root: Path) -> str:
    return os.path.relpath(Path(sound_path).resolve(), framescript_root)


def portable_slides(slides: list[dict], framescript_root: Path) -> list[dict]:
    result = []
    for slide in slides:
        portable = dict(slide)
        portable["soundPath"] = relative_sound_path(slide["soundPath"], framescript_root)
        result.append(portable)
    return result


def render_project_tsx(slides: list[dict], framescript_root: Path, body: str, *, title: str) -> str:
    if not slides:
        raise ValueError("slides が空です。")
    slides_json = json.dumps(portable_slides(slides, framescript_root), ensure_ascii=False, indent=2)
    return (
        HEADER.replace("__TITLE__", json.dumps(title, ensure_ascii=False))
        + f"\nconst SLIDES: Slide[] = {slides_json}\n"
        + body
    )


HEADER = '''import { Clip, ClipSequence } from "../src/lib/clip"
import { seconds, useCurrentFrame } from "../src/lib/frame"
import { FillFrame } from "../src/lib/layout/fill-frame"
import { Project, type ProjectSettings } from "../src/lib/project"
import { Sound } from "../src/lib/sound/sound"
import { TimeLine } from "../src/lib/timeline"

export const PROJECT_SETTINGS: ProjectSettings = {
  name: __TITLE__,
  width: 1920,
  height: 1080,
  fps: 30,
}

const CHANNEL_LABEL = "TOEIC 復習"

// prism-studio (~/prism-studio/prism_studio/render/framescript_export.py) の
// Glass/Background/Motion・配色をそのまま採用（実際に公開されている動画の配色。
// 暗い紺より目に優しいというユーザー指摘を反映）。
const BG = "#f4efe6"
const INK = "#191512"
const MUTED = "#6f665f"
const CARD = "rgba(255, 251, 245, 0.76)"
const BORDER = "rgba(25, 21, 18, 0.10)"
const SHADOW = "0 28px 90px rgba(44, 30, 20, 0.10)"
const ACCENT = "#275d72"
const ACCENT_SOFT = "rgba(39, 93, 114, 0.13)"
const ACCENT_GLOW = "rgba(39, 93, 114, 0.16)"

const easeOut = (t: number) => 1 - Math.pow(1 - Math.min(1, Math.max(0, t)), 3)
const rise = (frame: number, delaySeconds: number, durationSeconds = 0.75) =>
  easeOut((frame - seconds(delaySeconds)) / seconds(durationSeconds))

const Motion = ({ delay = 0, y = 24, children }: { delay?: number; y?: number; children: React.ReactNode }) => {
  const frame = useCurrentFrame()
  const p = rise(frame, delay)
  return <div style={{ opacity: p, transform: `translateY(${y * (1 - p)}px)` }}>{children}</div>
}

const Glass = ({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) => (
  <div
    style={{
      background: CARD,
      border: `1px solid ${BORDER}`,
      boxShadow: SHADOW,
      borderRadius: 20,
      backdropFilter: "blur(12px)",
      ...style,
    }}
  >
    {children}
  </div>
)

const Background = ({ index, total }: { index: number; total: number }) => {
  const frame = useCurrentFrame()
  const p = rise(frame, 0, 1.1)
  const drift = frame * 0.22
  return (
    <>
      <FillFrame style={{ background: `linear-gradient(135deg, ${BG} 0%, #efe7db 46%, #f9f4ed 100%)` }} />
      <div
        style={{
          position: "absolute", left: -180 + drift * 0.15, top: 20 - 22 * (1 - p), width: 620, height: 620,
          borderRadius: 999, background: `radial-gradient(circle at 50% 50%, ${ACCENT_GLOW}, transparent 68%)`,
          filter: "blur(10px)",
        }}
      />
      <div
        style={{
          position: "absolute", right: -200 - drift * 0.1, bottom: -160 + 28 * p, width: 620, height: 620,
          borderRadius: 999, background: `radial-gradient(circle at 50% 50%, ${ACCENT_GLOW}, transparent 68%)`,
          filter: "blur(10px)",
        }}
      />
      <div style={{ position: "absolute", inset: 24, borderRadius: 32, border: `1px solid ${BORDER}` }} />
      <div
        style={{
          position: "absolute", left: 80, right: 80, top: 48, display: "flex", justifyContent: "space-between",
          alignItems: "center", color: MUTED,
        }}
      >
        <div style={{ fontSize: 17, letterSpacing: 3.4, fontWeight: 700 }}>{CHANNEL_LABEL}</div>
        <div style={{ fontSize: 17, letterSpacing: 3 }}>
          {String(index + 1).padStart(2, "0")} / {String(total).padStart(2, "0")}
        </div>
      </div>
    </>
  )
}

const Kicker = ({ text }: { text: string }) => (
  <div
    style={{
      display: "inline-flex", alignItems: "center", gap: 12, padding: "10px 18px", borderRadius: 999,
      background: ACCENT_SOFT, color: ACCENT, fontSize: 20, fontWeight: 800, letterSpacing: 2,
    }}
  >
    <div style={{ width: 9, height: 9, borderRadius: 999, background: ACCENT }} />
    {text}
  </div>
)

type CaptionCue = { start: number; end: number; text: string }

const _activeCue = (cues: CaptionCue[], t: number) => cues.find((cue) => t >= cue.start && t < cue.end)

// 日英2言語同時字幕。src/lib/captions/captions.tsx はcueごとに独立してbottom固定で
// 絶対配置するため、片方が2行に折り返すと重なる。1つのflexコンテナに積み、下端固定の
// まま上に伸びる形にすることで、テキスト長に関わらず重ならないようにする。
const DualCaptions = ({ en, ja }: { en: CaptionCue[]; ja: CaptionCue[] }) => {
  const frame = useCurrentFrame()
  const t = PROJECT_SETTINGS.fps > 0 ? frame / PROJECT_SETTINGS.fps : 0
  const activeEn = _activeCue(en, t)
  const activeJa = _activeCue(ja, t)
  if (!activeEn && !activeJa) return null

  const box: React.CSSProperties = {
    background: "rgba(10, 8, 6, 0.72)", color: "#fdfaf5", borderRadius: 14, padding: "14px 26px", fontSize: 28,
    lineHeight: 1.4, fontWeight: 700, fontFamily: '"Hiragino Sans", "Yu Gothic", sans-serif', textAlign: "center",
    maxWidth: "100%",
  }

  return (
    <div
      style={{
        position: "absolute", left: "8%", right: "8%", bottom: 36, display: "flex", flexDirection: "column",
        gap: 12, alignItems: "center", pointerEvents: "none",
      }}
    >
      {activeEn ? <div style={box}>{activeEn.text}</div> : null}
      {activeJa ? <div style={box}>{activeJa.text}</div> : null}
    </div>
  )
}
'''
