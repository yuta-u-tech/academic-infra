#!/usr/bin/env python3
"""描画済み DOM から layout_report.json を実測する。

4案を公平に比べるには、同じ方法で寸法・色・階層を取る必要がある。手計算の
レポートは案ごとに書き手の解釈が入るので、ブラウザに実際に描かせて
getBoundingClientRect と getComputedStyle から取る。

対象要素の選び方（全案共通の規則）:
- 直接テキストを持つ要素 → role=text
- button / input → role=button（tappable）
- テキストが無く、背景か境界線が見える要素 → role=shape
- 見えないもの・幅高さ0・レイアウト用の器は除外

rank はフォントサイズの降順で 1/2/3 に割り当てる（案ごとのクラス名に依存しない）。

usage: python3 dump_layout.py                    # 全案×全画面
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SCREENS = ("02-grammar", "03-vocab", "04-reading")
VARIANTS = {
    "current": HERE.parent.parent / "web" / "index.html",
    "editorial": HERE / "variants" / "editorial" / "index.html",
    "luminous": HERE / "variants" / "luminous" / "index.html",
    "momentum": HERE / "variants" / "momentum" / "index.html",
}

EXTRACTOR = r"""
<script>
(async () => {
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  for (let i = 0; i < 60 && !document.documentElement.dataset.ready; i++) await wait(100);
  await wait(300);

  const parseRgba = (value) => {
    const m = String(value).match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(",").map((x) => parseFloat(x));
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  };
  const hex = (c) => "#" + [c.r, c.g, c.b]
    .map((v) => Math.round(v).toString(16).padStart(2, "0")).join("");
  const toHex = (value) => {
    const c = parseRgba(value);
    return c && c.a > 0 ? hex(c) : null;
  };
  // 実効背景色。半透明の面はここで下地と合成する。
  // 合成しないと rgba(255,255,255,.04) のガラス面が「白」と測られ、
  // その上の文字が偽のコントラスト違反になる。
  const effectiveBg = (el) => {
    const stack = [];
    for (let n = el; n && n !== document.documentElement; n = n.parentElement) {
      const c = parseRgba(getComputedStyle(n).backgroundColor);
      if (!c || c.a === 0) continue;
      stack.push(c);
      if (c.a >= 1) break;
    }
    const base = parseRgba(getComputedStyle(document.documentElement).backgroundColor);
    let out = (base && base.a >= 1) ? base : { r: 0, g: 0, b: 0, a: 1 };
    for (const layer of stack.reverse()) {
      out = {
        r: layer.r * layer.a + out.r * (1 - layer.a),
        g: layer.g * layer.a + out.g * (1 - layer.a),
        b: layer.b * layer.a + out.b * (1 - layer.a),
        a: 1,
      };
    }
    return hex(out);
  };
  const directText = (el) => Array.from(el.childNodes)
    .filter((n) => n.nodeType === 3).map((n) => n.textContent.trim()).join(" ").trim();

  const W = window.innerWidth, H = window.innerHeight;
  const out = [];
  let index = 0;
  for (const el of document.querySelectorAll("body *")) {
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden" || +style.opacity === 0) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;

    const tag = el.tagName.toLowerCase();
    const text = directText(el);
    const tappable = tag === "button" || tag === "input" || tag === "select";
    const hasSurface = toHex(style.backgroundColor) !== null
      || parseFloat(style.borderTopWidth) > 0 || parseFloat(style.borderBottomWidth) > 0;
    if (!text && !tappable && !hasSurface) continue;      // レイアウト用の器は除外
    if (!text && !tappable && r.height > H * 0.7) continue; // 全面の背景板も除外

    const role = tappable ? "button" : (text ? "text" : "shape");
    out.push({
      id: `${tag}-${index++}${el.id ? "-" + el.id : ""}`,
      bbox: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)],
      role,
      font_size: text || tappable ? Math.round(parseFloat(style.fontSize)) : null,
      font_weight: text || tappable ? style.fontWeight : null,
      color: text || tappable ? toHex(style.color) : null,
      bg_color: effectiveBg(el),
      text: text || null,
      tappable,
      overflow: r.left < -1 || r.top < -1 || r.right > W + 1 || r.bottom > H + 1,
    });
  }

  // rank: フォントサイズの降順で 1/2/3。案ごとのクラス名に依存させない。
  const sizes = [...new Set(out.filter((e) => e.font_size).map((e) => e.font_size))]
    .sort((a, b) => b - a);
  const rankOf = (size) => {
    const i = sizes.indexOf(size);
    if (i < 0) return 3;
    return i === 0 ? 1 : (i <= Math.max(1, Math.floor(sizes.length / 3)) ? 2 : 3);
  };
  for (const e of out) e.rank = e.font_size ? rankOf(e.font_size) : 3;

  const report = {
    canvas: { width: W, height: H, bg_color: effectiveBg(document.body) },
    safe_area: { top: 0, bottom: 0, left: 24, right: 24 },
    renderer: "html_static",
    elements: out,
    meta: { screen: document.documentElement.dataset.screen || "unknown" },
  };
  const holder = document.createElement("script");
  holder.type = "application/json";
  holder.id = "__layout";
  holder.textContent = JSON.stringify(report);
  document.body.appendChild(holder);
  document.documentElement.dataset.layout = "1";
})();
</script>
"""


def build_pages(name: str, source: Path) -> Path:
    """make_preview の仕組みを使って、抽出器つきプレビューを作る。"""
    import make_preview

    out_dir = HERE / "layout" / name
    out_dir.mkdir(parents=True, exist_ok=True)
    original_source, original_here = make_preview.SOURCE, make_preview.HERE
    make_preview.SOURCE, make_preview.HERE = source, out_dir
    try:
        for screen in SCREENS:
            path = make_preview.build(screen, make_preview.SCENES[screen])
            html = path.read_text(encoding="utf-8")
            html = html.replace("</body>", EXTRACTOR + "</body>", 1)
            path.write_text(html, encoding="utf-8")
    finally:
        make_preview.SOURCE, make_preview.HERE = original_source, original_here
    return out_dir


def dump(page: Path, tag: str) -> dict | None:
    """chrome --dump-dom で描画後の DOM を取り、埋め込んだ JSON を抜く。

    Chrome は DOM を吐いたあとも終了しないので、プロセスの終了を待たない。
    出力をファイルへ流し、目印が現れたら kill する（communicate で待つと
    タイムアウト時に出力ごと捨ててしまう）。
    """
    dump_path = Path(f"/tmp/dump-{tag}.html")
    dump_path.unlink(missing_ok=True)
    with dump_path.open("w") as sink:
        process = subprocess.Popen(
            [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
             "--window-size=1440,900", "--virtual-time-budget=9000",
             f"--user-data-dir=/tmp/dump-profile-{tag}", "--dump-dom", f"file://{page}"],
            stdout=sink, stderr=subprocess.DEVNULL, text=True,
        )
        try:
            for _ in range(60):
                time.sleep(0.5)
                if dump_path.exists() and "__layout" in dump_path.read_text(errors="replace"):
                    break
        finally:
            process.kill()
            process.wait(timeout=10)

    html = dump_path.read_text(errors="replace")
    match = re.search(r'<script type="application/json" id="__layout">(.*?)</script>', html, re.S)
    return json.loads(match.group(1)) if match else None


def main() -> None:
    for name, source in VARIANTS.items():
        if not source.exists():
            print(f"skip {name}: {source} が無い")
            continue
        out_dir = build_pages(name, source)
        for screen in SCREENS:
            report = dump(out_dir / f"{screen}.preview.html", f"{name}-{screen}")
            if report is None:
                print(f"{name}/{screen}: 抽出できず")
                continue
            destination = out_dir / f"{screen}.layout_report.json"
            destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{name}/{screen}: {len(report['elements'])} 要素 -> {destination.name}")
            time.sleep(0.2)


if __name__ == "__main__":
    main()
