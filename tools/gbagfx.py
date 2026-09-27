#!/usr/bin/env python3
"""Generate GBA-legal art, and refuse to emit art that is not.

    python3 tools/gbagfx.py

Fonts are not made here: they are listed in assets-src/fonts.toml and built
by tools/gbafont.py, which reuses the helpers and checks below.

Output goes to gba/gfx/ and is committed, so the build never depends on
Pillow, on a font, or on this script. Regeneration is deliberate.

Two ideas here are worth keeping in any project:

  * Everything is quantised to the GBA's 15-bit colour, so a PNG preview is
    exactly what the hardware shows.
  * The checks at the bottom fail the run rather than emitting art the
    hardware will not take. A palette overflow is a build error here instead
    of a mystery on device.

See AGENTS.md sections 4 and 6.
"""

import argparse
import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "gba" / "gfx"

SCREEN = (240, 160)


def q(c):
    """Snap a channel to the GBA's 5 bits per channel."""
    return (c >> 3) << 3


def rgb(r, g, b):
    return (q(r), q(g), q(b), 255)


# The panel colour. Tile fonts drawn onto it (`bg` in assets-src/fonts.toml)
# must use the same value.
NIGHT = rgb(24, 28, 40)


def gen_panel():
    """A flat field, so panels and menus can be written as tiles over it."""
    save(Image.new("RGBA", SCREEN, NIGHT), "panel.png")


def fit(im, box):
    """Scale to fit inside `box`, preserving aspect, after trimming."""
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
    w, h = im.size
    scale = min(box[0] / w, box[1] / h)
    return im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)


def flatten(im, background, colours=14):
    """Composite onto a flat field and reduce to one GBA palette.

    Keeping a whole background image inside 16 colours means no individual
    8x8 tile can overflow, which removes a whole class of problem.
    """
    field = Image.new("RGBA", im.size, background)
    field.alpha_composite(im.convert("RGBA"))
    reduced = field.convert("RGB").quantize(colors=colours, method=Image.MEDIANCUT)
    reduced = reduced.convert("RGBA")
    px = reduced.load()
    for y in range(reduced.size[1]):
        for x in range(reduced.size[0]):
            r, g, b, _ = px[x, y]
            px[x, y] = (q(r), q(g), q(b), 255)
    return reduced


# --- checks -------------------------------------------------------------


def pixels(im):
    """RGBA pixels as tuples (Image.getdata is deprecated)."""
    b = im.convert("RGBA").tobytes()
    return tuple(zip(b[0::4], b[1::4], b[2::4], b[3::4]))


def check_background(name):
    """One palette for the image, and tiles that fit a charblock."""
    im = Image.open(OUT / name).convert("RGBA")
    colours, tiles, worst = set(), set(), 0
    for ty in range(im.size[1] // 8):
        for tx in range(im.size[0] // 8):
            data = pixels(im.crop((tx * 8, ty * 8, tx * 8 + 8, ty * 8 + 8)))
            tiles.add(data)
            worst = max(worst, len(set(data)))
            colours |= set(data)
    problems = []
    if worst > 16:
        problems.append(f"a tile uses {worst} colours (max 16)")
    if len(colours) > 16:
        problems.append(f"{len(colours)} colours overall (want <= 16 for one palette)")
    if len(tiles) > 512:
        problems.append(f"{len(tiles)} unique tiles (a charblock holds 512)")
    print(
        f"  {name:20} colours={len(colours):3} worst-tile={worst:2} "
        f"tiles={len(tiles):4} {'; '.join(problems) or 'ok'}"
    )
    return not problems


# The only sprite sizes the hardware has. 24x24 is famously not one of them:
# draw 24x24 of art centred in a 32x32 frame instead.
LEGAL_SPRITE_SIZES = {
    (8, 8), (16, 16), (32, 32), (64, 64),
    (16, 8), (32, 8), (32, 16), (64, 32),
    (8, 16), (8, 32), (16, 32), (32, 64),
}


def check_sprites(name, w, h=None):
    """15 colours plus transparent per frame, and a legal frame size."""
    h = h or Image.open(OUT / name).size[1]
    im = Image.open(OUT / name).convert("RGBA")
    problems = []
    if (w, h) not in LEGAL_SPRITE_SIZES:
        problems.append(f"{w}x{h} is not a legal sprite size")
    worst = 0
    for i in range(im.size[0] // w):
        frame = im.crop((i * w, 0, i * w + w, h))
        worst = max(worst, len({p for p in pixels(frame) if p[3] > 0}))
    if worst > 15:
        problems.append(f"a frame uses {worst} colours (max 15 + transparent)")
    print(f"  {name:20} {w}x{h} worst-frame={worst:2} {'; '.join(problems) or 'ok'}")
    return not problems


def save(im, name):
    (OUT / name).parent.mkdir(parents=True, exist_ok=True)
    im.save(OUT / name)
    print(f"  {name:24} {im.size[0]:4}x{im.size[1]:<4}")


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    print("generating")
    gen_panel()

    print("checking GBA limits")
    if not check_background("panel.png"):
        sys.exit("art violates a GBA limit; see above")


if __name__ == "__main__":
    main()
