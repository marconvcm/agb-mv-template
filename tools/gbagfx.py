#!/usr/bin/env python3
"""Generate GBA-legal art, and refuse to emit art that is not.

    python3 tools/gbagfx.py [--font PATH] [--size N]

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

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "gba" / "gfx"

SCREEN = (240, 160)

# Glyphs available to both text systems. Keep them in sync with the Rust
# side's CHARSET; index in this string is the tile/frame index.
CHARSET = " 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ:$+-./!?"
DIGITS = "0123456789+- "


def q(c):
    """Snap a channel to the GBA's 5 bits per channel."""
    return (c >> 3) << 3


def rgb(r, g, b):
    return (q(r), q(g), q(b), 255)


TRANSPARENT = (0, 0, 0, 0)
BLACK = rgb(0, 0, 0)
WHITE = rgb(255, 255, 255)
DIM = rgb(112, 126, 133)
PANEL = rgb(155, 173, 183)
NIGHT = rgb(24, 28, 40)
GOLD = rgb(255, 205, 60)


def load_font(path, size):
    """Load a pixel font and refuse it if it antialiases at this size.

    A font rendered off its design size produces grey edge pixels, which a
    15-bit indexed palette cannot afford. Checking here saves discovering it
    on a 3x-scaled emulator window.
    """
    font = ImageFont.truetype(str(path), size)
    probe = Image.new("L", (200, 32), 0)
    ImageDraw.Draw(probe).text((0, 0), CHARSET.strip(), font=font, fill=255)
    aa = sum(1 for p in probe.getdata() if 0 < p < 255)
    if aa:
        sys.exit(
            f"{Path(path).name} at {size}px antialiases ({aa} grey pixels).\n"
            "Use the font's design size, or pick a font drawn on a pixel grid."
        )
    advance = font.getlength("MM") / 2
    print(f"font {Path(path).name} @{size}px: advance {advance:g}px, no antialiasing")
    return font, int(advance)


def glyph(ch, font, fg, bg):
    """One 8x8 cell holding `ch`, left-aligned."""
    im = Image.new("RGBA", (8, 8), bg)
    if ch != " ":
        mask = Image.new("L", (8, 8), 0)
        ImageDraw.Draw(mask).text((0, -2), ch, font=font, fill=255)
        ink = Image.new("RGBA", (8, 8), fg)
        im.paste(ink, (0, 0), mask.point(lambda v: 255 if v > 127 else 0))
    return im


def gen_charsets(font):
    """Background text tiles, one variant per surface colour.

    BG palette index 0 is the global backdrop, not per-tile transparency, so
    a text tile carries the colour of whatever it sits on. Add a variant here
    for every panel colour the game writes text onto.
    """
    for name, fg, bg in [
        ("charset_dark", WHITE, NIGHT),
        ("charset_dim", DIM, NIGHT),
        ("charset_panel", BLACK, PANEL),
    ]:
        sheet = Image.new("RGBA", (8 * len(CHARSET), 8), bg)
        for i, ch in enumerate(CHARSET):
            sheet.paste(glyph(ch, font, fg, bg), (i * 8, 0))
        save(sheet, f"{name}.png")


def gen_font(font):
    """An object version of the charset, in two inks.

    Objects sit at the font's natural advance instead of the 8px tile grid,
    so menus set tight. Two inks so unavailable entries can be dimmed.
    """
    n = len(CHARSET)
    sheet = Image.new("RGBA", (8 * n * 2, 8), TRANSPARENT)
    for i, ch in enumerate(CHARSET):
        sheet.paste(glyph(ch, font, WHITE, TRANSPARENT), (i * 8, 0))
        sheet.paste(glyph(ch, font, DIM, TRANSPARENT), ((n + i) * 8, 0))
    save(sheet, "font.png")


def gen_digits(font):
    """Digits as objects, in two colours, for values that change every frame."""
    n = len(DIGITS)
    sheet = Image.new("RGBA", (8 * n * 2, 8), TRANSPARENT)
    for i, ch in enumerate(DIGITS):
        sheet.paste(glyph(ch, font, WHITE, TRANSPARENT), (i * 8, 0))
        sheet.paste(glyph(ch, font, GOLD, TRANSPARENT), ((n + i) * 8, 0))
    save(sheet, "digits.png")


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


def check_background(name):
    """One palette for the image, and tiles that fit a charblock."""
    im = Image.open(OUT / name).convert("RGBA")
    colours, tiles, worst = set(), set(), 0
    for ty in range(im.size[1] // 8):
        for tx in range(im.size[0] // 8):
            data = tuple(im.crop((tx * 8, ty * 8, tx * 8 + 8, ty * 8 + 8)).getdata())
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
        worst = max(worst, len({p for p in frame.getdata() if p[3] > 0}))
    if worst > 15:
        problems.append(f"a frame uses {worst} colours (max 15 + transparent)")
    print(f"  {name:20} {w}x{h} worst-frame={worst:2} {'; '.join(problems) or 'ok'}")
    return not problems


def save(im, name):
    OUT.mkdir(parents=True, exist_ok=True)
    im.save(OUT / name)
    print(f"  {name:20} {im.size[0]:4}x{im.size[1]:<4}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--font",
        default="assets-src/font.ttf",
        help="pixel font, rendered at its design size (default: %(default)s)",
    )
    ap.add_argument("--size", type=int, default=8, help="font size in px")
    args = ap.parse_args()

    path = Path(args.font)
    if not path.is_absolute():
        path = REPO / path
    if not path.exists():
        sys.exit(
            f"font not found: {path}\n"
            "Drop a pixel font there or pass --font. Kenney Mini Square Mono at\n"
            "8px is known to render with no antialiasing; see AGENTS.md section 5."
        )

    font, _ = load_font(path, args.size)
    print("generating")
    gen_charsets(font)
    gen_font(font)
    gen_digits(font)
    gen_panel()

    print("checking GBA limits")
    ok = True
    for bg in ("panel.png", "charset_dark.png", "charset_dim.png", "charset_panel.png"):
        ok &= check_background(bg)
    ok &= check_sprites("font.png", 8, 8)
    ok &= check_sprites("digits.png", 8, 8)
    if not ok:
        sys.exit("art violates a GBA limit; see above")


if __name__ == "__main__":
    main()
