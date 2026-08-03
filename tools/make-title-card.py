"""Render the promo's title card - which is also its README thumbnail.

GitHub's inline video player is generated from a bare `user-attachments` URL and
its markdown sanitiser strips author-written `<video>`, so there is no `poster`
attribute a README can set. The browser simply shows frame 0. The promo opens on
a generative hero clip that begins dark while the light builds, so the
repository front page showed an all-but-empty rectangle until somebody pressed
play.

A still card at the head of the edit fixes the thumbnail and reads as a title
rather than as a workaround: whoever lands here can see what the video is before
deciding to spend a minute on it.

The card composites `assets/logo-dark.png` rather than redrawing the mark, so it
cannot drift from the logo the rest of the project uses, and it takes its
palette and typefaces from tools/make-promo.py so the card and the film that
follows it are the same piece of design.

Usage:  python tools/make-title-card.py
Output: assets/poster.png
"""

import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

W, H = 1920, 1080

# Straight out of tools/make-promo.py - the film's own palette.
BG = (4, 17, 35)
PANEL = (11, 26, 48)
EDGE = (37, 52, 78)
TXT = (230, 237, 243)
DIM = (139, 148, 158)
GREEN = (16, 163, 127)
CYAN = (121, 192, 255)

FONTS = {
    "bold": "C:/Windows/Fonts/segoeuib.ttf",
    "ui": "C:/Windows/Fonts/segoeui.ttf",
    "monob": "C:/Windows/Fonts/consolab.ttf",
}
FALLBACKS = {
    "bold": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "ui": ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    "monob": ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"],
}
_cache = {}


def F(kind, size):
    key = (kind, size)
    if key not in _cache:
        for path in [FONTS[kind]] + FALLBACKS.get(kind, []):
            if os.path.isfile(path):
                _cache[key] = ImageFont.truetype(path, size)
                break
        else:
            _cache[key] = ImageFont.load_default()
    return _cache[key]


_probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))


def tw(s, f):
    return _probe.textlength(s, font=f)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


# Every line here is a claim the repository already makes. The command is the
# product's entire interface, the sentence is the README's own subtitle, and the
# strip is the badge row. Nothing is invented for the sake of a nice card.
CMD = "/to-codex"
LINE = "Conversation, skills, instructions and memory — intact."
STRIP = "WINDOWS  ·  MACOS  ·  LINUX      PYTHON 3.9+  ·  MIT"


def main():
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    for x in range(0, W, 64):
        for y in range(0, H, 64):
            d.point((x, y), fill=(8, 24, 44))

    logo_path = ASSETS / "logo-dark.png"
    if not logo_path.exists():
        raise SystemExit("missing {}".format(logo_path))
    logo = Image.open(logo_path).convert("RGBA")

    # Scaled to a fixed width and centred on its own drawn bounds rather than on
    # the canvas, because a transparent PNG's padding is rarely symmetric and
    # centring the file instead of the artwork leaves the mark visibly off.
    target = 1000
    scale = target / logo.width
    logo = logo.resize((target, max(1, int(logo.height * scale))), Image.LANCZOS)
    bbox = logo.getbbox()
    art_cx = (bbox[0] + bbox[2]) / 2
    top = 300
    im.paste(logo, (int(W / 2 - art_cx), top), logo)

    y = top + (bbox[3] - bbox[1]) + 78

    # The command, drawn as the terminal token it is. It is the whole interface,
    # so it earns the most weight on the card after the mark itself.
    fc = F("monob", 62)
    pad_x, pad_y = 46, 26
    cw = tw(CMD, fc) + pad_x * 2
    ch = 62 + pad_y * 2
    box = [W / 2 - cw / 2, y, W / 2 + cw / 2, y + ch]
    d.rounded_rectangle(box, radius=14, fill=PANEL, outline=EDGE, width=2)
    d.text((W / 2 - tw(CMD, fc) / 2, y + pad_y - 6), CMD, font=fc, fill=CYAN)

    fl = F("bold", 42)
    d.text((W / 2 - tw(LINE, fl) / 2, y + ch + 44), LINE, font=fl, fill=TXT)

    rule_y = y + ch + 136
    half = 320
    for i in range(half * 2):
        d.line([W / 2 - half + i, rule_y, W / 2 - half + i, rule_y + 5],
               fill=lerp(CYAN, GREEN, i / (half * 2)))

    fs = F("monob", 26)
    d.text((W / 2 - tw(STRIP, fs) / 2, rule_y + 40), STRIP, font=fs,
           fill=lerp(BG, DIM, 0.92))

    out = ASSETS / "poster.png"
    im.save(out)
    print("wrote {} ({}x{})".format(out, W, H))
    return 0


if __name__ == "__main__":
    sys.exit(main())
