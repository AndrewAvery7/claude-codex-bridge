"""Render the claude-codex-bridge promo's motion-graphics core (1920x1080 @ 24fps).

This produces the precise product scenes - terminal, /to-codex, model picker,
transfer, hand-off, install command - where exact text matters and generative
video models are unreliable (they garble long strings). It is designed to be
stitched between two AI-generated bookends by tools/stitch-promo.sh:

  [ AI hero shot ] -> [ THIS: product scenes ] -> [ AI end card ]

Design rules (learned the hard way from review):
  * No bounce / spring / elastic motion. Fades and micro-slides (<= 8px) only.
  * No dead space. Compositions fill the frame; elements are large; holds short.
  * Every string is rendered from source text, so commands are always exact.

Usage:  python tools/make-promo.py [--outdir DIR]
Output: DIR/core.mp4 (needs ffmpeg on PATH)
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1920, 1080, 24

# Palette - BG matches the AI end card exactly so the stitch is seamless.
BG = (4, 17, 35)
PANEL = (11, 26, 48)
WIN = (13, 22, 40)
EDGE = (37, 52, 78)
TXT = (230, 237, 243)
DIM = (139, 148, 158)
ORANGE = (217, 119, 87)
GREEN = (16, 163, 127)
CYAN = (121, 192, 255)
AMBER = (210, 153, 34)
RED = (218, 79, 62)
WHITE = (255, 255, 255)

FONTS = {
    "bold": "C:/Windows/Fonts/segoeuib.ttf",
    "semi": "C:/Windows/Fonts/seguisb.ttf",
    "ui": "C:/Windows/Fonts/segoeui.ttf",
    "mono": "C:/Windows/Fonts/consola.ttf",
    "monob": "C:/Windows/Fonts/consolab.ttf",
}
_cache = {}


def F(kind, size):
    key = (kind, size)
    if key not in _cache:
        try:
            _cache[key] = ImageFont.truetype(FONTS[kind], size)
        except OSError:
            _cache[key] = ImageFont.load_default()
    return _cache[key]


_probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))


def tw(s, f):
    return _probe.textlength(s, font=f)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def ease(t):
    """Smooth ease-out with NO overshoot (deliberately not a spring)."""
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def fade(color, a):
    return lerp(BG, color, max(0.0, min(1.0, a)))


def base():
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    for x in range(0, W, 64):
        for y in range(0, H, 64):
            d.point((x, y), fill=(10, 26, 48))
    return im


def shadowed_panel(im, box, radius=18, fill=WIN, edge=EDGE, width=2):
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(
        [box[0] + 4, box[1] + 12, box[2] + 4, box[3] + 12], radius=radius, fill=(0, 0, 0, 130)
    )
    blurred = sh.filter(ImageFilter.GaussianBlur(14))
    im.paste(Image.alpha_composite(im.convert("RGBA"), blurred).convert("RGB"), (0, 0))
    ImageDraw.Draw(im).rounded_rectangle(box, radius=radius, fill=fill, outline=edge, width=width)


def window(im, box, title, accent=DIM, dim=1.0):
    """Terminal-style window. Returns content origin (x, y)."""
    shadowed_panel(im, box, fill=lerp(BG, WIN, dim))
    d = ImageDraw.Draw(im)
    bar = box[1] + 60
    d.line([box[0] + 2, bar, box[2] - 2, bar], fill=lerp(BG, EDGE, dim), width=2)
    for i, c in enumerate((ORANGE, AMBER, GREEN)):
        cx = box[0] + 38 + i * 34
        d.ellipse([cx - 9, box[1] + 21, cx + 9, box[1] + 39], fill=lerp(BG, c, dim))
    d.text((box[0] + 152, box[1] + 17), title, font=F("ui", 26), fill=fade(accent, dim))
    return box[0] + 46, bar + 30


HEAD_Y = 88


def headline(im, text, alpha=1.0, sub=None, sub_alpha=None):
    d = ImageDraw.Draw(im)
    d.text((120, HEAD_Y), text, font=F("bold", 66), fill=fade(TXT, alpha))
    if sub:
        d.text((123, HEAD_Y + 88), sub, font=F("ui", 34),
               fill=fade(DIM, alpha if sub_alpha is None else sub_alpha))


def gradient_bar(im, box, t, r=9):
    d = ImageDraw.Draw(im)
    d.rounded_rectangle(box, radius=r, fill=PANEL, outline=EDGE, width=2)
    x0, y0, x1, y1 = box
    inner = (x1 - x0) - 12
    n = int(inner * max(0.0, min(1.0, t)))
    for i in range(n):
        d.line([x0 + 6 + i, y0 + 6, x0 + 6 + i, y1 - 6], fill=lerp(ORANGE, GREEN, i / max(1, inner)))


# --------------------------------------------------------------------------
# content
# --------------------------------------------------------------------------
CONVO = [
    ("you", ["refactor the auth middleware to", "use the new token store"]),
    ("cc", ["Done - 4 files changed. Tests pass.", "Next: the session cache?"]),
    ("you", ["yes, and keep the retry", "semantics identical"]),
    ("cc", ["Working through it - the retry path", "has an edge case at zero..."]),
]
CMD = "/to-codex"
MODELS = ["GPT-5.6-Sol", "GPT-5.6-Terra", "GPT-5.6-Luna", "GPT-5.4-Mini"]
TRAVELS = ["CONVERSATION", "SKILLS", "INSTRUCTIONS", "MEMORY"]
INSTALL = "claude plugin marketplace add AndrewAvery7/claude-codex-bridge"

BIG_WIN = [120, 258, 1800, 1000]


def draw_convo(im, box, origin, n, alpha=1.0, size=30):
    """Chat transcript inside a window box. Returns next y."""
    d = ImageDraw.Draw(im)
    x, y = origin
    right = box[2] - 46
    f = F("mono", size)
    lh = size + 8
    for who, lines in CONVO[:n]:
        if who == "you":
            wpx = max(tw(l, f) for l in lines)
            bx0 = right - wpx - 40
            d.rounded_rectangle([bx0, y - 8, right, y + lh * len(lines) + 8],
                                radius=12, fill=fade(PANEL, alpha))
            for i, l in enumerate(lines):
                d.text((bx0 + 20, y + i * lh), l, font=f, fill=fade(TXT, alpha))
        else:
            for i, l in enumerate(lines):
                d.text((x, y + i * lh), l, font=f, fill=fade(DIM, alpha))
        y += lh * len(lines) + 34
    return y


def scene_problem(fr, n):
    im = base()
    t = fr / n
    ox, oy = window(im, BIG_WIN, "Claude Code - your-project")
    draw_convo(im, BIG_WIN, (ox, oy), 4, alpha=min(1.0, fr / 8))
    d = ImageDraw.Draw(im)
    if t > 0.26:
        p = ease((t - 0.26) / 0.44)
        pct = 62 + int(33 * p)
        bx = [ox, BIG_WIN[3] - 92, BIG_WIN[2] - 46, BIG_WIN[3] - 54]
        d.rounded_rectangle(bx, radius=9, fill=PANEL, outline=EDGE, width=2)
        nf = int((bx[2] - bx[0] - 12) * pct / 100)
        col = lerp(AMBER, RED, max(0.0, (pct - 78) / 22))
        d.rounded_rectangle([bx[0] + 6, bx[1] + 6, bx[0] + 6 + nf, bx[3] - 6], radius=6, fill=col)
        d.text((ox, BIG_WIN[3] - 148), f"context window   {pct}%", font=F("mono", 27), fill=col)
    headline(im, "Hours of context.",
             alpha=min(1.0, max(0.0, (t - 0.08) / 0.16)),
             sub="One token limit away from starting over.",
             sub_alpha=min(1.0, max(0.0, (t - 0.32) / 0.20)))
    return im


def scene_command(fr, n):
    im = base()
    t = fr / n
    ox, oy = window(im, BIG_WIN, "Claude Code - your-project")
    y = draw_convo(im, BIG_WIN, (ox, oy), 4, alpha=0.5)
    d = ImageDraw.Draw(im)
    typed = CMD[: max(0, min(len(CMD), int((t - 0.16) / 0.28 * len(CMD)) + 1))] if t > 0.16 else ""
    f = F("monob", 52)
    d.text((ox, y + 20), ">", font=f, fill=DIM)
    d.text((ox + 46, y + 20), typed, font=f, fill=CYAN)
    if t > 0.16 and int(fr / 6) % 2 == 0:
        cx = ox + 46 + tw(typed, f)
        d.rectangle([cx + 4, y + 26, cx + 26, y + 78], fill=TXT)
    headline(im, "One command.", alpha=min(1.0, t / 0.12))
    return im


def scene_picker(fr, n):
    im = base()
    t = fr / n
    d = ImageDraw.Draw(im)
    headline(im, "Pick your model.", alpha=min(1.0, t / 0.12))
    seq = [1, 2, 1, 0, 0, 0]
    idx = seq[min(len(seq) - 1, int(t * len(seq)))]
    chosen = t > 0.60
    px, pw, py = 300, 1320, 268
    row = 168
    shadowed_panel(im, [px, py, px + pw, py + 32 + row * len(MODELS)], radius=22, fill=PANEL)
    f = F("semi", 58)
    for i, m in enumerate(MODELS):
        ry = py + 20 + i * row
        sel = i == idx
        if sel:
            d.rounded_rectangle([px + 18, ry, px + pw - 18, ry + row - 18], radius=16,
                                fill=GREEN if chosen else (30, 44, 68))
        d.text((px + 64, ry + 30), m, font=f, fill=WHITE if (sel and chosen) else (TXT if sel else DIM))
        if i == 0:
            d.text((px + 64 + tw(m, f) + 30, ry + 50), "recommended", font=F("ui", 34),
                   fill=WHITE if chosen else fade(GREEN, 0.9))
        if sel and chosen:
            d.text((px + pw - 96, ry + 26), "OK", font=F("bold", 50), fill=WHITE)
    return im


def scene_transfer(fr, n):
    im = base()
    t = fr / n
    d = ImageDraw.Draw(im)
    headline(im, "Session transferred.", alpha=min(1.0, t / 0.12))
    ox = 240
    f = F("mono", 40)
    d.text((ox, 330), "Transferring Claude session -> Codex thread...",
           font=f, fill=fade(TXT, min(1.0, t / 0.10)))
    gradient_bar(im, [ox, 410, ox + 1420, 462], ease(min(1.0, max(0.0, (t - 0.10) / 0.34))))
    rows = [
        ("verified independently in Codex's state DB", DIM, 0.48),
        ("SUCCESS   thread 019f9574-5820-76c2", GREEN, 0.60),
        ("Opened the Codex desktop app on this thread.", GREEN, 0.74),
    ]
    y = 530
    for text, col, at in rows:
        if t >= at:
            d.text((ox, y), text, font=f, fill=fade(col, min(1.0, (t - at) / 0.08)))
        y += 66
    if t > 0.86:
        d.text((ox, 760), "(not the plugin's broken success message - issue #513)",
               font=F("ui", 32), fill=fade(DIM, min(1.0, (t - 0.86) / 0.10)))
    return im


def scene_arrive(fr, n):
    im = base()
    t = fr / n
    slide = int((1 - ease(min(1.0, t / 0.32))) * 480)
    cc = [90, 300, 940, 980]
    ox1, oy1 = window(im, cc, "Claude Code", dim=0.42)
    draw_convo(im, cc, (ox1, oy1), 3, alpha=0.30, size=26)
    cx = [1000 + slide, 258, 1850 + slide, 1010]
    ox, oy = window(im, cx, "your-project - Codex", accent=GREEN)
    d = ImageDraw.Draw(im)
    y = draw_convo(im, cx, (ox, oy), 4, alpha=min(1.0, max(0.0, (t - 0.28) / 0.18)), size=26)
    if t > 0.54:
        d.text((ox, y + 6), "picking up exactly where Claude left off",
               font=F("mono", 28), fill=fade(GREEN, min(1.0, (t - 0.54) / 0.14)))
    d.rounded_rectangle([ox, cx[3] - 112, cx[2] - 46, cx[3] - 44], radius=14,
                        fill=PANEL, outline=EDGE, width=2)
    d.text((ox + 24, cx[3] - 96), "Work with Codex", font=F("ui", 28), fill=DIM)
    d.rounded_rectangle([cx[2] - 250, cx[3] - 100, cx[2] - 62, cx[3] - 56], radius=11, fill=(30, 44, 68))
    d.text((cx[2] - 232, cx[3] - 94), "5.6 Sol", font=F("ui", 26), fill=GREEN)
    headline(im, "Codex opens on your conversation.", alpha=min(1.0, t / 0.12))
    return im


def scene_travels(fr, n):
    im = base()
    t = fr / n
    d = ImageDraw.Draw(im)
    headline(im, "Everything comes with it.", alpha=min(1.0, t / 0.12))
    gap, cw, ch, top = 30, 420, 280, 400
    x0 = (W - (cw * 4 + gap * 3)) // 2
    for i, label in enumerate(TRAVELS):
        a = ease(min(1.0, max(0.0, (t - (0.18 + i * 0.12)) / 0.14)))
        if a <= 0:
            continue
        dy = int((1 - a) * 8)
        bx = [x0 + i * (cw + gap), top + dy, x0 + i * (cw + gap) + cw, top + ch + dy]
        col = lerp(ORANGE, GREEN, i / 3)
        d.rounded_rectangle(bx, radius=18, fill=fade(PANEL, a), outline=fade(col, a * 0.85), width=3)
        f = F("semi", 40) if len(label) <= 11 else F("semi", 34)
        d.text(((bx[0] + bx[2]) / 2 - tw(label, f) / 2, (bx[1] + bx[3]) / 2 - 26),
               label, font=f, fill=fade(TXT, a))
        d.rounded_rectangle([bx[0] + 40, bx[3] - 34, bx[2] - 40, bx[3] - 26], radius=4,
                            fill=fade(col, a * 0.9))
    if t > 0.72:
        a = min(1.0, (t - 0.72) / 0.14)
        s = "same skills. same instructions. same memory."
        f = F("ui", 42)
        d.text((W / 2 - tw(s, f) / 2, 782), s, font=f, fill=fade(DIM, a))
    return im


def scene_install(fr, n):
    im = base()
    t = fr / n
    d = ImageDraw.Draw(im)
    headline(im, "Install it in one line.", alpha=min(1.0, t / 0.12))
    f = F("mono", 42)
    cwid = tw(INSTALL, f)
    a = ease(min(1.0, max(0.0, (t - 0.12) / 0.20)))
    if a > 0:
        bx = [W / 2 - cwid / 2 - 54, 392, W / 2 + cwid / 2 + 54, 490]
        d.rounded_rectangle(bx, radius=16, fill=fade(PANEL, a), outline=fade(GREEN, a * 0.75), width=3)
        d.text((W / 2 - cwid / 2, 418), INSTALL, font=f, fill=fade(GREEN, a))
    if t > 0.40:
        a2 = min(1.0, (t - 0.40) / 0.16)
        s = "Free and open source - MIT"
        f2 = F("semi", 52)
        d.text((W / 2 - tw(s, f2) / 2, 588), s, font=f2, fill=fade(TXT, a2))
    if t > 0.56:
        a3 = min(1.0, (t - 0.56) / 0.16)
        s = "github.com/AndrewAvery7/claude-codex-bridge"
        f3 = F("ui", 44)
        d.text((W / 2 - tw(s, f3) / 2, 686), s, font=f3, fill=fade(DIM, a3))
    if t > 0.70:
        a4 = min(1.0, (t - 0.70) / 0.18)
        y, half = 800, 420
        for i in range(half * 2):
            d.line([W / 2 - half + i, y, W / 2 - half + i, y + 7],
                   fill=fade(lerp(ORANGE, GREEN, i / (half * 2)), a4))
    return im


# Frame counts are tuned for READABILITY, not brevity: a viewer has to be able
# to read the terminal, follow the command being typed, and take in each screen.
# All animation inside a scene is expressed as a fraction of its length, so
# raising these numbers genuinely slows the motion (including the typing) rather
# than just holding a static frame for longer.
SCENES = [
    (scene_problem, 184),   # 7.67s - read the conversation + watch the meter climb
    (scene_command, 170),   # 7.08s - typing is legible character by character
    (scene_picker, 184),    # 7.67s - follow the selection landing
    (scene_transfer, 264),  # 11.00s - four lines of output land one at a time;
                            #          this scene carries the payoff, so it holds
                            #          noticeably longer than the others
    (scene_arrive, 208),    # 8.67s - most text on screen; needs the most time
    (scene_travels, 160),   # 6.67s
    (scene_install, 192),   # 8.00s - read and memorise the install command
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=str(Path(__file__).resolve().parent.parent / "assets"))
    args = ap.parse_args()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    tmp = Path(tempfile.mkdtemp(prefix="ccb-promo-"))
    idx = 0
    for fn, count in SCENES:
        for fr in range(count):
            fn(fr, count).save(tmp / f"f{idx:05d}.png")
            idx += 1
        print(f"  {fn.__name__}: {count} frames")
    print(f"total {idx} frames = {idx / FPS:.1f}s")

    if not shutil.which("ffmpeg"):
        print("ffmpeg not found - frames left in", tmp)
        return 1
    core = out / "core.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(FPS), "-i", str(tmp / "f%05d.png"),
         "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", str(core)],
        check=True, capture_output=True,
    )
    print("wrote", core)
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
