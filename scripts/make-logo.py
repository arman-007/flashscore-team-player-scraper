"""Generate the Apify Store logo.

Constraints it is drawn against:

* It must read at **76x76**, the Store card size, and still be recognisable at
  38px: no text, no fine strokes.
* It must not resemble Flashscore's branding (dark navy, red-pink accent,
  lightning-bolt wordmark). This shares the deep indigo and teal of the other
  Flashscore Actors in this account, so they read as one family.

The mark is a team shirt -- light body, teal collar and stripe -- with a
ball in the bottom-right corner.

Usage:  python scripts/make-logo.py [out.png] [size]
"""

from __future__ import annotations

import sys

from PIL import Image, ImageDraw

BG = (30, 27, 75)
ROW = (129, 140, 248)
ROW_LIGHT = (226, 232, 240)
ACCENT = (45, 212, 191)

SUPERSAMPLE = 4


def draw_logo(size: int) -> Image.Image:
    s = size * SUPERSAMPLE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=BG)

    # The shirt, in unit coordinates: shoulders, sleeves, body.
    shirt = [
        (0.38, 0.18), (0.62, 0.18), (0.86, 0.30), (0.78, 0.46), (0.70, 0.42),
        (0.70, 0.84), (0.30, 0.84), (0.30, 0.42), (0.22, 0.46), (0.14, 0.30),
    ]
    d.polygon([(x * s, y * s) for x, y in shirt], fill=ROW_LIGHT)

    # Collar: a teal V cut into the neckline.
    d.polygon([(0.38 * s, 0.18 * s), (0.62 * s, 0.18 * s), (0.50 * s, 0.31 * s)], fill=ACCENT)
    d.polygon([(0.43 * s, 0.18 * s), (0.57 * s, 0.18 * s), (0.50 * s, 0.25 * s)], fill=BG)

    # A vertical stripe down the body.
    d.rectangle([0.45 * s, 0.31 * s, 0.55 * s, 0.84 * s], fill=ROW)

    # The ball, bottom right, ringed in the background colour so it sits on top.
    cx, cy, r = s * 0.76, s * 0.76, s * 0.12
    ring = r + s * 0.025
    d.ellipse([cx - ring, cy - ring, cx + ring, cy + ring], fill=BG)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ACCENT)
    d.regular_polygon((cx, cy, r * 0.42), 5, rotation=18, fill=BG)

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "logo.png"
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 512
    draw_logo(size).save(out, "PNG")
    print(f"wrote {out} at {size}x{size}")


if __name__ == "__main__":
    main()
