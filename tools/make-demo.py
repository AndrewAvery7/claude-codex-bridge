"""Generate the README demo animation (GIF + MP4) for claude-codex-bridge.

Fully synthetic - no screen recording, no personal data. Re-run any time:

    python tools/make-demo.py

Outputs: assets/demo.gif and assets/demo.mp4 (mp4 needs ffmpeg on PATH).
Fonts: Windows Consolas + Segoe UI (falls back to PIL default elsewhere).
"""

import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1200, 630
FPS = 12
REPO = Path(__file__).resolve().parent.parent
OUT_GIF = REPO / "assets" / "demo.gif"
OUT_MP4 = REPO / "assets" / "demo.mp4"

# ---------- palette (matches the social card) ----------
BG = (13, 17, 23)
GRID = (22, 28, 36)
WIN = (22, 27, 34)
WIN_EDGE = (48, 54, 61)
TXT = (230, 237, 243)
DIM = (139, 148, 158)
ORANGE = (217, 119, 87)
GREEN = (16, 163, 127)
CYAN = (121, 192, 255)
YELLOW = (210, 153, 34)
SUCCESS = (63, 185, 80)
PANEL = (18, 23, 33)


def font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


MONO = lambda s: font("C:/Windows/Fonts/consola.ttf", s)
UI = lambda s: font("C:/Windows/Fonts/segoeui.ttf", s)
UIB = lambda s: font("C:/Windows/Fonts/segoeuib.ttf", s)


def ease_out(t):
    return 1 - (1 - t) ** 3


def base_frame():
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    for x in range(0, W, 40):
        for y in range(0, H, 40):
            d.ellipse([x - 1, y - 1, x + 1, y + 1], fill=GRID)
    return im


def rounded(d, box, r, fill, outline=None, width=1):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def window(im, box, title, title_color=DIM):
    """Draw a terminal-style window; returns the content origin (x, y)."""
    d = ImageDraw.Draw(im)
    # soft shadow
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(
        [box[0] + 6, box[1] + 10, box[2] + 6, box[3] + 10], radius=16, fill=(0, 0, 0, 110)
    )
    im.paste(Image.alpha_composite(im.convert("RGBA"), sh.filter(ImageFilter.GaussianBlur(8))).convert("RGB"), (0, 0))
    d = ImageDraw.Draw(im)
    rounded(d, box, 14, WIN, WIN_EDGE, 2)
    # header
    d.line([box[0] + 1, box[1] + 44, box[2] - 1, box[1] + 44], fill=WIN_EDGE, width=2)
    for i, c in enumerate([ORANGE, YELLOW, GREEN]):
        cx = box[0] + 26 + i * 26
        d.ellipse([cx - 7, box[1] + 15, cx + 7, box[1] + 29], fill=c)
    d.text((box[0] + 110, box[1] + 12), title, font=UI(19), fill=title_color)
    return box[0] + 30, box[1] + 64


LH = 30  # terminal line height


def term_lines(im, origin, lines, cursor_at=None, blink_on=True):
    d = ImageDraw.Draw(im)
    x0, y0 = origin
    for i, (text, color) in enumerate(lines):
        d.text((x0, y0 + i * LH), text, font=MONO(19), fill=color)
    if cursor_at is not None and blink_on:
        row, col_px = cursor_at
        cx = x0 + col_px
        cy = y0 + row * LH
        d.rectangle([cx, cy + 2, cx + 11, cy + 24], fill=TXT)


def text_w(s, f):
    return ImageDraw.Draw(Image.new("RGB", (1, 1))).textlength(s, font=f)


MODELS = ["GPT-5.6-Sol   (Recommended)", "GPT-5.6-Terra", "GPT-5.6-Luna", "GPT-5.4-Mini"]


def picker(im, top_left, highlight, selected=False):
    d = ImageDraw.Draw(im)
    x, y = top_left
    w, row_h = 480, 38
    box = [x, y, x + w, y + 10 + row_h * len(MODELS) + 10]
    rounded(d, box, 10, PANEL, WIN_EDGE, 2)
    d.text((x + 16, y - 30), "Which Codex model should the thread resume on?", font=UI(17), fill=DIM)
    for i, m in enumerate(MODELS):
        ry = y + 10 + i * row_h
        if i == highlight:
            color = GREEN if selected else (35, 45, 60)
            rounded(d, [x + 8, ry, x + w - 8, ry + row_h - 6], 8, color)
            fill = (255, 255, 255) if selected else TXT
        else:
            fill = DIM
        d.text((x + 24, ry + 5), m, font=UI(18), fill=fill)
        if i == highlight and selected:
            d.text((x + w - 40, ry + 5), "✓", font=UIB(18), fill=(255, 255, 255))


def progress_bar(im, box, t):
    d = ImageDraw.Draw(im)
    rounded(d, box, 6, PANEL, WIN_EDGE, 1)
    if t <= 0:
        return
    x0, y0, x1, y1 = box
    fill_w = int((x1 - x0 - 8) * min(t, 1.0))
    if fill_w > 4:
        for i in range(fill_w):
            f = i / max(1, (x1 - x0 - 8))
            c = tuple(int(ORANGE[j] + (GREEN[j] - ORANGE[j]) * f) for j in range(3))
            d.line([x0 + 4 + i, y0 + 4, x0 + 4 + i, y1 - 4], fill=c)


def badge_logo(im, cx, cy, s=1.0):
    """CC ->> CX badge motif."""
    d = ImageDraw.Draw(im)
    bw, bh, gap = int(96 * s), int(72 * s), int(52 * s)
    r = int(16 * s)
    x1 = cx - gap // 2 - bw
    x2 = cx + gap // 2
    y = cy - bh // 2
    rounded(d, [x1, y, x1 + bw, y + bh], r, ORANGE)
    rounded(d, [x2, y, x2 + bw, y + bh], r, GREEN)
    f = UIB(int(30 * s))
    d.text((x1 + bw / 2 - text_w("CC", f) / 2, cy - int(21 * s)), "CC", font=f, fill=(255, 255, 255))
    d.text((x2 + bw / 2 - text_w("CX", f) / 2, cy - int(21 * s)), "CX", font=f, fill=(255, 255, 255))
    aw = int(9 * s)
    pts = [(cx - int(10 * s), cy - int(16 * s)), (cx + int(10 * s), cy), (cx - int(10 * s), cy + int(16 * s))]
    d.line(pts, fill=TXT, width=aw, joint="curve")


# ---------- scene rendering ----------
frames = []
durations = []


def emit(im, ms=int(1000 / FPS)):
    frames.append(im)
    durations.append(ms)


CMD = "/to-codex"
TERM_BOX = [70, 60, 720, 480]

INFO_LINES = [("Found the live transcript - matches this session.", DIM)]
XFER = [
    ("Transferring Claude session -> Codex thread...", TXT),
]
DONE = [
    ("SUCCESS  thread: 019f-demo-thread", SUCCESS),
    ("Opened the Codex desktop app on this thread.", GREEN),
]

# S1: type the command (with blinking cursor)
for n in range(len(CMD) + 1):
    im = base_frame()
    ox, oy = window(im, TERM_BOX, "Claude Code")
    typed = CMD[:n]
    term_lines(im, (ox, oy), [("> " + typed, CYAN)], cursor_at=(0, int(text_w("> " + typed, MONO(19)))), blink_on=True)
    emit(im, 70)
for blink in range(4):
    im = base_frame()
    ox, oy = window(im, TERM_BOX, "Claude Code")
    term_lines(im, (ox, oy), [("> " + CMD, CYAN)], cursor_at=(0, int(text_w("> " + CMD, MONO(19)))), blink_on=blink % 2 == 0)
    emit(im, 190)

# S2: info + model picker; highlight steps 0->0 (settle on recommended), select
for step, sel in [(0, False), (1, False), (2, False), (1, False), (0, False), (0, True)]:
    for hold in range(4 if not sel else 8):
        im = base_frame()
        ox, oy = window(im, TERM_BOX, "Claude Code")
        term_lines(im, (ox, oy), [("> " + CMD, CYAN)] + INFO_LINES)
        picker(im, (ox + 10, oy + 3 * LH + 8), step, sel)
        emit(im, 90)

# S3: transfer progress
for t in range(14):
    im = base_frame()
    ox, oy = window(im, TERM_BOX, "Claude Code")
    lines = [("> " + CMD, CYAN)] + INFO_LINES + [("Model: GPT-5.6-Sol", GREEN), ("", TXT)] + XFER
    term_lines(im, (ox, oy), lines)
    progress_bar(im, [ox, oy + 6 * LH, ox + 560, oy + 6 * LH + 22], ease_out(t / 13))
    emit(im, 90)

# S3b: success lines
for hold in range(10):
    im = base_frame()
    ox, oy = window(im, TERM_BOX, "Claude Code")
    lines = [("> " + CMD, CYAN)] + INFO_LINES + [("Model: GPT-5.6-Sol", GREEN), ("", TXT)] + XFER
    term_lines(im, (ox, oy), lines)
    progress_bar(im, [ox, oy + 6 * LH, ox + 560, oy + 6 * LH + 22], 1.0)
    shown = DONE if hold >= 3 else DONE[:1]
    term_lines(im, (ox, oy + int(7.2 * LH)), shown)
    emit(im, 130)

# S4: Codex window slides in from the right
CODEX_FINAL = [560, 90, 1130, 560]


def codex_window(im, shift):
    box = [CODEX_FINAL[0] + shift, CODEX_FINAL[1], CODEX_FINAL[2] + shift, CODEX_FINAL[3]]
    ox, oy = window(im, box, "your-project - Codex", title_color=GREEN)
    d = ImageDraw.Draw(im)
    x = box[0] + 28
    # conversation: carried-over turns
    rounded(d, [x, oy + 6, x + 420, oy + 60], 10, PANEL)
    d.text((x + 14, oy + 14), "...continuing right where Claude left", font=UI(16), fill=DIM)
    d.text((x + 14, oy + 34), "off - full conversation imported.", font=UI(16), fill=DIM)
    rounded(d, [box[2] - 240 - 28, oy + 84, box[2] - 28, oy + 126], 10, (40, 48, 64))
    d.text((box[2] - 240 - 12, oy + 94), "ship the next feature", font=UI(16), fill=TXT)
    for i, wl in enumerate([300, 420, 360, 180]):
        rounded(d, [x, oy + 160 + i * 34, x + wl, oy + 178 + i * 34], 6, (40, 48, 60))
    # composer
    rounded(d, [x, box[3] - 88, box[2] - 28, box[3] - 30], 12, PANEL, WIN_EDGE, 2)
    d.text((x + 16, box[3] - 76), "Work with Codex", font=UI(17), fill=DIM)
    rounded(d, [box[2] - 150, box[3] - 78, box[2] - 44, box[3] - 42], 9, (40, 48, 64))
    d.text((box[2] - 138, box[3] - 72), "5.6 Sol", font=UI(16), fill=GREEN)


for t in range(12):
    im = base_frame()
    ox, oy = window(im, TERM_BOX, "Claude Code")
    lines = [("> " + CMD, CYAN)] + INFO_LINES + [("Model: GPT-5.6-Sol", GREEN), ("", TXT)] + XFER
    term_lines(im, (ox, oy), lines)
    progress_bar(im, [ox, oy + 6 * LH, ox + 560, oy + 6 * LH + 22], 1.0)
    term_lines(im, (ox, oy + int(7.2 * LH)), DONE)
    codex_window(im, int((1 - ease_out(t / 11)) * 640))
    emit(im, 80)
for hold in range(22):
    im = base_frame()
    ox, oy = window(im, TERM_BOX, "Claude Code")
    lines = [("> " + CMD, CYAN)] + INFO_LINES + [("Model: GPT-5.6-Sol", GREEN), ("", TXT)] + XFER
    term_lines(im, (ox, oy), lines)
    progress_bar(im, [ox, oy + 6 * LH, ox + 560, oy + 6 * LH + 22], 1.0)
    term_lines(im, (ox, oy + int(7.2 * LH)), DONE)
    codex_window(im, 0)
    emit(im, 110)

# S5: end card
for t in range(30):
    im = base_frame()
    a = ease_out(min(1.0, t / 8))
    d = ImageDraw.Draw(im)
    badge_logo(im, W // 2, 170, 1.15)
    title = "claude-codex-bridge"
    f = UIB(52)
    d.text((W / 2 - text_w(title, f) / 2, 250), title, font=f, fill=tuple(int(c * a) for c in TXT))
    tag = "handoff context. keep momentum."
    f2 = UI(26)
    d.text((W / 2 - text_w(tag, f2) / 2, 330), tag, font=f2, fill=tuple(int(c * a) for c in DIM))
    cmdline = "claude plugin marketplace add AndrewAvery7/claude-codex-bridge"
    f3 = MONO(21)
    cw = text_w(cmdline, f3)
    rounded(d, [W / 2 - cw / 2 - 26, 408, W / 2 + cw / 2 + 26, 462], 12, PANEL, WIN_EDGE, 2)
    d.text((W / 2 - cw / 2, 422), cmdline, font=f3, fill=GREEN)
    foot = "CONVERSATION  •  SKILLS  •  INSTRUCTIONS  •  MEMORY"
    f4 = UI(19)
    d.text((W / 2 - text_w(foot, f4) / 2, 520), foot, font=f4, fill=tuple(int(c * a) for c in DIM))
    emit(im, 110 if t < 29 else 900)

# ---------- write outputs ----------
OUT_GIF.parent.mkdir(exist_ok=True)
frames[0].save(
    OUT_GIF,
    save_all=True,
    append_images=frames[1:],
    duration=durations,
    loop=0,
    optimize=True,
)
print(f"GIF: {OUT_GIF} ({OUT_GIF.stat().st_size/1e6:.2f} MB, {len(frames)} frames)")

if shutil.which("ffmpeg"):
    tmp = Path(tempfile.mkdtemp())
    concat = tmp / "list.txt"
    with open(concat, "w") as fh:
        for i, (fr, ms) in enumerate(zip(frames, durations)):
            p = tmp / f"f{i:04d}.png"
            fr.save(p)
            fh.write(f"file '{p.as_posix()}'\nduration {ms/1000:.3f}\n")
        fh.write(f"file '{(tmp / f'f{len(frames)-1:04d}.png').as_posix()}'\n")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
         "-vf", "format=yuv420p", "-r", "24", str(OUT_MP4)],
        check=True, capture_output=True,
    )
    print(f"MP4: {OUT_MP4} ({OUT_MP4.stat().st_size/1e6:.2f} MB)")
    shutil.rmtree(tmp, ignore_errors=True)
else:
    print("ffmpeg not found - skipped MP4")
