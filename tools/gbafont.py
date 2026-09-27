#!/usr/bin/env python3
"""Build every font in the game from one manifest, and refuse fonts that will not work.

    python3 tools/gbafont.py probe FONT [--sizes 5-24] [--charset STR]
    python3 tools/gbafont.py preview FONT --size N [--text STR] [--scale 4]
    python3 tools/gbafont.py build [--manifest assets-src/fonts.toml] [--only NAME]

`probe` answers the question that matters before anything else: at which
sizes does this font rasterise with zero antialiased pixels? A pixel font
is only crisp at its design size (or a multiple of it), and a 15-bit
indexed palette cannot afford grey edge pixels.

`preview` draws sample text the way the GBA would get it -- snapped to whole
pixels and 15-bit colour -- scaled up so you can judge it, next to the
font's own smooth rendering. It works on any font, including ones `build`
refuses, so you can see what you would lose.

FONT is a file path or an installed family name ('Saira ExtraCondensed
Thin'), which is looked up with fc-match.

`build` reads assets-src/fonts.toml (the format is documented there) and
writes, for every font listed:

  objects  gba/gfx/fonts/<name>.png, a transparent strip of sprite frames
           with every variant's glyphs end to end. The frame is the smallest
           legal sprite size that fits, so an 8px font gives 8x8 and a 12px
           one 8x16 or 16x16.
  tiles    gba/gfx/fonts/<name>_<variant>.png, one per surface colour, since
           BG palette index 0 is the global backdrop rather than
           transparency. Glyphs larger than 8px span several tiles.

and one gba/src/gfx/fonts.rs holding a module per font, so charsets, advances
and variant offsets are never typed by hand and cannot drift from the art.

Output is committed like the rest of the art, so the build never depends on
Pillow or on the fonts. See AGENTS.md sections 5 and 6.
"""

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import gbagfx
from gbagfx import LEGAL_SPRITE_SIZES, REPO, q

MANIFEST = REPO / "assets-src" / "fonts.toml"
SHEETS = "fonts"  # under gba/gfx/
RUST_OUT = REPO / "gba" / "src" / "gfx" / "fonts.rs"
ASSETS_RS = REPO / "gba" / "src" / "gfx" / "assets.rs"
TRANSPARENT = (0, 0, 0, 0)
THRESHOLD = 128
# Names the generated module already uses; a variant cannot take them.
RESERVED = {"charset", "advance", "widths", "line_height", "cell"}


def parse_colour(text):
    """'#rrggbb' or 'rrggbb', snapped to 15-bit."""
    h = text.lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        raise ValueError(f"expected #rrggbb, got {text!r}")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return (q(r), q(g), q(b), 255)


def parse_range(text):
    lo, _, hi = text.partition("-")
    return range(int(lo), int(hi or lo) + 1)


def parse_cell(text):
    w, _, h = text.lower().partition("x")
    return int(w), int(h or w)


# --- measuring ----------------------------------------------------------


class Metrics:
    """Where a charset's ink sits, relative to the draw origin.

    `left` and `top` come from the font's whole printable-ASCII range, not
    just this charset, so two sheets cut from the same font at the same size
    share a baseline: a digits-only sheet lines up with the full alphabet
    next to it. `right` and `bottom` are the charset's own, so the cell is
    no bigger than its glyphs need.
    """

    def __init__(self, font, charset):
        def inked(chars):
            boxes = [font.getbbox(ch) for ch in chars if ch != " "]
            return [b for b in boxes if b[2] > b[0] and b[3] > b[1]]

        boxes = inked(charset)
        if not boxes:
            raise ValueError("none of the charset's glyphs have any ink in this font")
        ascii_boxes = inked(chr(c) for c in range(33, 127)) + boxes
        self.left = min(b[0] for b in ascii_boxes)
        self.top = min(b[1] for b in ascii_boxes)
        self.right = max(b[2] for b in boxes)
        self.bottom = max(b[3] for b in boxes)
        # Font-wide too, so every sheet of one font reports one line height.
        self.line = max(b[3] for b in ascii_boxes) - self.top
        self.widths = [round(font.getlength(ch)) for ch in charset]
        self.advance = max(self.widths)
        self.mono = len(set(self.widths)) == 1

    @property
    def ink_w(self):
        return self.right - self.left

    @property
    def ink_h(self):
        return self.bottom - self.top


def grey_pixels(font, charset):
    """Antialiased pixels in the whole charset. Zero is the goal."""
    m = Metrics(font, charset)
    w = sum(max(1, x) for x in m.widths) + m.ink_w + 4
    probe = Image.new("L", (w, m.bottom + 4), 0)
    ImageDraw.Draw(probe).text((2, 2), charset, font=font, fill=255)
    return sum(1 for p in probe.tobytes() if 0 < p < 255)


def ceil8(n):
    return (n + 7) // 8 * 8


def sprite_cell(w, h):
    """Smallest legal sprite frame that holds w x h, or None."""
    fits = [s for s in LEGAL_SPRITE_SIZES if s[0] >= w and s[1] >= h]
    return min(fits, key=lambda s: (s[0] * s[1], s[1])) if fits else None


# --- probe --------------------------------------------------------------


def find_font(name):
    """A path, or failing that an installed family name via fc-match."""
    path = Path(name).expanduser()
    if path.exists():
        return path
    try:
        out = subprocess.run(
            ["fc-match", "-f", "%{file}\n%{family}:%{style}", name],
            capture_output=True, text=True, check=True,
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        sys.exit(f"font not found: {name} (and fc-match is unavailable)")
    # fc-match always answers with *something*; only trust it if every word
    # asked for appears in what it matched.
    matched = " ".join(out[1:]).lower().replace(" ", "")
    if not out or not all(w in matched for w in name.lower().split()):
        sys.exit(f"font not found: {name!r} (fc-match only offered {' '.join(out[1:]) or 'nothing'})")
    print(f"{name} -> {out[0]}")
    return Path(out[0])


def cmd_probe(args):
    path = find_font(args.font)
    print(f"{path.name}  charset={len(args.charset)} glyphs\n")
    print(" size  grey  ink     advance       sprite  tiles")
    crisp = []
    for size in args.sizes:
        font = ImageFont.truetype(str(path), size)
        m = Metrics(font, args.charset)
        aa = grey_pixels(font, args.charset)
        adv = f"{m.advance}px" + ("" if m.mono else " (prop)")
        cell = sprite_cell(max(m.advance, m.ink_w), m.ink_h)
        cell = f"{cell[0]}x{cell[1]}" if cell else "none"
        tiles = f"{ceil8(max(m.advance, m.ink_w)) // 8}x{ceil8(m.ink_h) // 8}"
        mark = "  <- crisp" if aa == 0 else ""
        print(f" {size:4}  {aa:4}  {m.ink_w:2}x{m.ink_h:<3}  {adv:12}  {cell:6}  {tiles:5}{mark}")
        if aa == 0:
            crisp.append(size)
    print()
    if crisp:
        print(f"crisp at: {', '.join(map(str, crisp))}px -- use one of these as `size`")
    else:
        sys.exit(
            "no size in range renders without antialiasing; this is not a pixel\n"
            "font. Widen --sizes, or pick a font drawn on a pixel grid."
        )


# --- preview ------------------------------------------------------------


def cmd_preview(args):
    path = find_font(args.font)
    font = ImageFont.truetype(str(path), args.size)
    ink, bg = parse_colour(args.ink), parse_colour(args.bg)
    lines = args.text.split("|")
    pad, gap = 4, 2

    # Size the canvas from the real ink of every line.
    boxes = [font.getbbox(line) for line in lines]
    top = min(b[1] for b in boxes)
    line_h = max(b[3] for b in boxes) - top
    w = max(b[2] for b in boxes) + pad * 2
    h = (line_h + gap) * len(lines) - gap + pad * 2

    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    for i, line in enumerate(lines):
        draw.text((pad, pad - top + i * (line_h + gap)), line, font=font, fill=255)
    grey = sum(1 for p in mask.tobytes() if 0 < p < 255)

    def paint(m):
        im = Image.new("RGBA", (w, h), bg)
        im.paste(Image.new("RGBA", (w, h), ink), (0, 0), m)
        return im.resize((w * args.scale, h * args.scale), Image.NEAREST)

    gba = paint(mask.point(lambda v: 255 if v >= args.threshold else 0))
    rows = [gba]
    if grey:
        rows.insert(0, paint(mask))  # the smooth original, for comparison
    sep = args.scale * 2
    sheet = Image.new("RGBA", (gba.width, sum(r.height for r in rows) + sep * (len(rows) - 1)), bg)
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height + sep

    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    wide = w - pad * 2
    print(f"{path.name} @{args.size}px: text is {wide}x{line_h}px ({wide * 100 // 240}% of the 240px screen)")
    if grey:
        print(
            f"antialiases ({grey} grey pixels): top is the font's own rendering, bottom\n"
            f"is what the GBA gets at --threshold {args.threshold}. `build` will refuse this size."
        )
    else:
        print("crisp: no antialiasing, what you see is what the GBA gets")
    print(f"wrote {out}")


# --- build --------------------------------------------------------------


class Font:
    """One [[font]] entry, validated and measured."""

    def __init__(self, entry):
        def need(key):
            if key not in entry:
                raise ValueError(f"missing `{key}`")
            return entry[key]

        self.name = need("name")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", self.name):
            raise ValueError("`name` must be snake_case: it becomes a Rust module")
        self.file = REPO / need("file")
        if not self.file.exists():
            raise ValueError(f"font not found: {self.file}")
        self.size = need("size")
        self.mode = need("mode")
        if self.mode not in ("objects", "tiles"):
            raise ValueError('`mode` is "objects" or "tiles"')
        self.charset = need("charset")
        if any(not (32 <= ord(c) < 127) for c in self.charset):
            raise ValueError("charset must be printable ASCII (it becomes a Rust b\"...\" literal)")
        if len(set(self.charset)) != len(self.charset):
            raise ValueError("charset has duplicate glyphs")
        self.leading = entry.get("leading", 2)

        raw = need("variants")
        if not raw:
            raise ValueError("needs at least one variant")
        self.variants = {}
        for v, spec in raw.items():
            if not re.fullmatch(r"[a-z][a-z0-9_]*", v):
                raise ValueError(f"variant `{v}` must be snake_case")
            if v in RESERVED:
                raise ValueError(f"variant `{v}` would clash with the generated `{v.upper()}`")
            if self.mode == "objects":
                if not isinstance(spec, str):
                    raise ValueError(f'objects variant `{v}` is just an ink: {v} = "#rrggbb"')
                self.variants[v] = (parse_colour(spec), TRANSPARENT)
            else:
                if not isinstance(spec, dict) or "ink" not in spec or "bg" not in spec:
                    raise ValueError(
                        f'tiles variant `{v}` needs its surface: {v} = {{ ink = "#..", bg = "#.." }}'
                    )
                self.variants[v] = (parse_colour(spec["ink"]), parse_colour(spec["bg"]))

        self.font = ImageFont.truetype(str(self.file), self.size)
        self.m = Metrics(self.font, self.charset)
        aa = grey_pixels(self.font, self.charset)
        if aa:
            raise ValueError(
                f"{self.file.name} at {self.size}px antialiases ({aa} grey pixels); "
                f"run `gbafont.py probe {entry['file']}` for crisp sizes"
            )

        need_w, need_h = max(self.m.advance, self.m.ink_w), self.m.ink_h
        if "cell" in entry:
            self.cell = parse_cell(entry["cell"])
        elif self.mode == "objects":
            self.cell = sprite_cell(need_w, need_h)
            if not self.cell:
                raise ValueError(f"{need_w}x{need_h} glyphs do not fit any sprite size (max 64x64)")
        else:
            self.cell = (ceil8(need_w), ceil8(need_h))
        if self.mode == "objects" and self.cell not in LEGAL_SPRITE_SIZES:
            raise ValueError(f"{self.cell[0]}x{self.cell[1]} is not a legal sprite size")
        if self.mode == "tiles" and (self.cell[0] % 8 or self.cell[1] % 8):
            raise ValueError("tile cells must be multiples of 8")
        if self.cell[0] < need_w or self.cell[1] < need_h:
            print(f"  warning: {self.name}: {need_w}x{need_h} ink clipped to {self.cell[0]}x{self.cell[1]}")

    def sheets(self):
        """(sheet path under gba/gfx/, glyph (ink, bg) per run) in output order."""
        if self.mode == "objects":
            return [(f"{SHEETS}/{self.name}.png", list(self.variants.values()))]
        return [(f"{SHEETS}/{self.name}_{v}.png", [c]) for v, c in self.variants.items()]

    def glyph(self, ch, ink, bg):
        """One glyph in a cell, ink pinned to the charset's top-left so every
        glyph shares a baseline."""
        im = Image.new("RGBA", self.cell, bg)
        if ch != " ":
            mask = Image.new("L", self.cell, 0)
            ImageDraw.Draw(mask).text((-self.m.left, -self.m.top), ch, font=self.font, fill=255)
            mask = mask.point(lambda v: 255 if v >= THRESHOLD else 0)
            im.paste(Image.new("RGBA", self.cell, ink), (0, 0), mask)
        return im

    def render(self, runs):
        """Runs of the charset end to end. Tiles are read row-major, so a
        glyph of cw x ch tiles puts its tile (tx, ty) at column g*cw + tx of
        tile row ty -- which is what the generated `tile()` computes."""
        w, h = self.cell
        n = len(self.charset)
        sheet = Image.new("RGBA", (w * n * len(runs), h), runs[0][1])
        for k, (ink, bg) in enumerate(runs):
            for i, ch in enumerate(self.charset):
                sheet.paste(self.glyph(ch, ink, bg), ((k * n + i) * w, 0))
        return sheet


def rust_bytes(s):
    return "".join("\\\\" if c == "\\" else '\\"' if c == '"' else c for c in s)


def rust_module(f):
    fold = any(c.isupper() for c in f.charset) and not any(c.islower() for c in f.charset)
    blank = f.charset.index(" ") if " " in f.charset else 0
    cw, ch = f.cell
    sheets = ", ".join(f"`gfx/{s}`" for s, _ in f.sheets())
    o = [
        f"pub mod {f.name} {{",
        f"    //! {f.file.name} @{f.size}px, {f.mode}, {cw}x{ch} cell. Sheets: {sheets}.",
        "",
        "    /// Glyphs in sheet order: the index is the frame or tile number.",
        f'    pub const CHARSET: &[u8] = b"{rust_bytes(f.charset)}";',
    ]
    if f.m.mono:
        o += ["    /// Pixels from one glyph to the next.", f"    pub const ADVANCE: i32 = {f.m.advance};"]
    else:
        widths = ", ".join(map(str, f.m.widths))
        o += ["    /// Per-glyph advance, indexed like `CHARSET`.", f"    pub const WIDTHS: &[u8] = &[{widths}];"]
    o += [
        f"    pub const LINE_HEIGHT: i32 = {f.m.line + f.leading};",
        f"    pub const CELL: (i32, i32) = ({cw}, {ch});",
    ]
    if f.mode == "objects":
        o.append("")
        o.append("    // Frame offset of each variant: frame = VARIANT + index(ch).")
        for k, v in enumerate(f.variants):
            o.append(f"    pub const {v.upper()}: usize = {k * len(f.charset)};")
    o += [
        "",
        f"    /// Glyph index for `ch`; anything not in the charset is {'blank' if ' ' in f.charset else 'glyph 0'}.",
        "    pub fn index(ch: u8) -> usize {",
        f"        super::lookup(CHARSET, {'true' if fold else 'false'}, {blank}, ch)",
        "    }",
        "",
        "    /// Pixel width of `text`.",
        "    pub fn width(text: &[u8]) -> i32 {",
    ]
    if f.m.mono:
        o.append("        text.len() as i32 * ADVANCE")
    else:
        o.append("        text.iter().map(|&c| WIDTHS[index(c)] as i32).sum()")
    o.append("    }")
    if f.mode == "tiles" and f.cell != (8, 8):
        tw, th = cw // 8, ch // 8
        o += [
            "",
            f"    /// Glyphs are {tw}x{th} tiles. Tile index of part (tx, ty) of glyph `g`.",
            "    pub fn tile(g: usize, tx: usize, ty: usize) -> usize {",
            f"        ty * CHARSET.len() * {tw} + g * {tw} + tx",
            "    }",
        ]
    o.append("}")
    return "\n".join(o)


def rust_file(fonts, manifest):
    head = f"""\
//! Every font in the game. GENERATED by `tools/gbafont.py` from
//! `{manifest.relative_to(REPO)}` -- edit that and run `make fonts`.
//!
//! The sheets themselves are wired into `assets.rs`.

// Each module exposes the same small API whether or not the game uses all of it.
#![allow(dead_code)]

fn lookup(charset: &[u8], fold: bool, blank: usize, ch: u8) -> usize {{
    let ch = if fold {{ ch.to_ascii_uppercase() }} else {{ ch }};
    charset.iter().position(|&g| g == ch).unwrap_or(blank)
}}
"""
    return head + "\n" + "\n\n".join(rust_module(f) for f in fonts) + "\n"


def cmd_build(args):
    manifest = Path(args.manifest).resolve()
    with open(manifest, "rb") as fh:
        entries = tomllib.load(fh).get("font", [])
    if not entries:
        sys.exit(f"{manifest}: no [[font]] entries")

    fonts, errors, seen = [], [], set()
    for i, entry in enumerate(entries):
        label = entry.get("name", f"font #{i + 1}")
        try:
            if label in seen:
                raise ValueError("duplicate name")
            seen.add(label)
            fonts.append(Font(entry))
        except (ValueError, OSError) as e:
            errors.append(f"  {label}: {e}")
    if errors:
        sys.exit(f"{manifest.name}:\n" + "\n".join(errors))

    # Sheet names must not collide: `a` + variant `b_c` and `a_b` + `c`.
    paths = [s for f in fonts for s, _ in f.sheets()]
    dupes = {p for p in paths if paths.count(p) > 1}
    if dupes:
        sys.exit(f"sheet names collide: {', '.join(sorted(dupes))}")

    only = [f for f in fonts if not args.only or f.name in args.only]
    if args.only and len(only) != len(set(args.only)):
        sys.exit(f"--only: unknown font; have {', '.join(f.name for f in fonts)}")

    print("generating")
    ok = True
    for f in only:
        for path, runs in f.sheets():
            gbagfx.save(f.render(runs), path)
    print("checking GBA limits")
    for f in only:
        for path, _ in f.sheets():
            if f.mode == "objects":
                ok &= gbagfx.check_sprites(path, *f.cell)
            else:
                ok &= gbagfx.check_background(path)
    if not ok:
        sys.exit("a font sheet violates a GBA limit; see above")

    # Stale sheets from renamed or removed fonts would otherwise linger.
    stale = sorted(
        str(p.relative_to(REPO))
        for p in (gbagfx.OUT / SHEETS).glob("*.png")
        if f"{SHEETS}/{p.name}" not in paths
    )

    # The Rust always covers every font, even with --only.
    RUST_OUT.write_text(rust_file(fonts, manifest))
    print(f"wrote {RUST_OUT.relative_to(REPO)} ({len(fonts)} fonts)")

    assets = ASSETS_RS.read_text() if ASSETS_RS.exists() else ""
    unwired = [p for p in paths if f'"gfx/{p}"' not in assets]
    for p in unwired:
        print(f"  note: gfx/{p} is not referenced in {ASSETS_RS.relative_to(REPO)} yet")
    for p in stale:
        print(f"  note: {p} is not in the manifest any more; delete it")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("probe", help="find the sizes a font renders crisply at")
    p.add_argument("font", help="TTF/OTF file or installed family name")
    p.add_argument("--sizes", type=parse_range, default=range(5, 25), help="e.g. 6-16 (default 5-24)")
    p.add_argument(
        "--charset",
        default=" 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.,:!?",
        help="glyphs to test",
    )
    p.set_defaults(func=cmd_probe)

    v = sub.add_parser("preview", help="render sample text as the GBA would, scaled up")
    v.add_argument("font", help="TTF/OTF file or installed family name")
    v.add_argument("--size", type=int, required=True, help="px")
    v.add_argument("--text", default="PRESS START|Score 0123456789", help="'|' separates lines")
    v.add_argument("--scale", type=int, default=4, help="nearest-neighbour zoom (default 4)")
    v.add_argument("--ink", default="#ffffff", help="#rrggbb (default white)")
    v.add_argument("--bg", default="#181c28", help="#rrggbb (default the template's panel)")
    v.add_argument("--threshold", type=int, default=128, help="0-255 cutoff for grey pixels")
    v.add_argument("--out", default=str(REPO / "target" / "font-preview.png"), help="default: target/font-preview.png")
    v.set_defaults(func=cmd_preview)

    b = sub.add_parser("build", help="generate every font in the manifest")
    b.add_argument("--manifest", default=str(MANIFEST), help="default: assets-src/fonts.toml")
    b.add_argument("--only", action="append", help="regenerate just this font's sheets (repeatable)")
    b.set_defaults(func=cmd_build)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
