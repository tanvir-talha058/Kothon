"""Generate Kothon logo assets: kothon_256.png, kothon.ico, kothon_logo.svg.

The mark: waveform bars hanging from a matra (মাত্রা) — the headstroke of
Bangla script. Voice (waveform) becoming Bangla writing (letters hang from
the matra). Jade on ink, matching the app palette.

Run from the repo root:  python assets/make_logo.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).parent

INK = (11, 16, 13, 255)       # --bg  #0b100d
JADE = (61, 214, 140, 255)    # --jade #3dd68c

# Geometry on a 256 canvas (scaled for other sizes).
# Matra headstroke, then 4 bars hanging from it: the syllable
# rhythm of "ko-thon" — short, tall, mid, low.
# Three strokes for the three letters ক থ ন, hanging from the matra.
# The middle stroke rises above the headline like a Bangla ascender, so
# the mark reads as script rather than dripping bars.
MATRA = (52, 88, 204, 110)                # x0, y0, x1, y1
BAR_W = 22
BAR_X = (74, 117, 160)
BAR_H = (72, 104, 52)                     # measured down from the matra top
BAR_RISE = (0, 32, 0)                     # extra height above the matra top
BAR_TOP = 88
TILE_RADIUS = 58


def _draw_mark(draw: ImageDraw.ImageDraw, scale: float) -> None:
    def s(v: float) -> float:
        return v * scale

    for x, h, rise in zip(BAR_X, BAR_H, BAR_RISE, strict=True):
        draw.rounded_rectangle(
            [s(x), s(BAR_TOP - rise), s(x + BAR_W), s(BAR_TOP + h)],
            radius=s(BAR_W / 2), fill=JADE,
        )
    draw.rounded_rectangle(
        [s(MATRA[0]), s(MATRA[1]), s(MATRA[2]), s(MATRA[3])],
        radius=s((MATRA[3] - MATRA[1]) / 2), fill=JADE,
    )


def make_tile(size: int) -> Image.Image:
    """Ink tile with the jade mark — app icon / ICO."""
    # Render at 4x and downscale so small ICO sizes stay crisp
    big = size * 4
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    scale = big / 256
    draw.rounded_rectangle([0, 0, big, big], radius=TILE_RADIUS * scale, fill=INK)
    _draw_mark(draw, scale)
    return img.resize((size, size), Image.LANCZOS)


def make_svg() -> str:
    bars = "\n".join(
        f'  <rect x="{x}" y="{BAR_TOP - rise}" width="{BAR_W}" height="{h + rise}" rx="{BAR_W // 2}"/>'
        for x, h, rise in zip(BAR_X, BAR_H, BAR_RISE, strict=True)
    )
    matra_h = MATRA[3] - MATRA[1]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
<rect width="256" height="256" rx="{TILE_RADIUS}" fill="#0b100d"/>
<g fill="#3dd68c">
{bars}
  <rect x="{MATRA[0]}" y="{MATRA[1]}" width="{MATRA[2] - MATRA[0]}" height="{matra_h}" rx="{matra_h // 2}"/>
</g>
</svg>
"""


def main() -> None:
    make_tile(256).save(ASSETS / "kothon_256.png")
    make_tile(256).save(
        ASSETS / "kothon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    (ASSETS / "kothon_logo.svg").write_text(make_svg(), encoding="utf-8")
    print(f"Wrote kothon_256.png, kothon.ico, kothon_logo.svg to {ASSETS}")


if __name__ == "__main__":
    main()
