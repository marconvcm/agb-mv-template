Source assets for `tools/gbagfx.py` and `tools/gbafont.py`. Not shipped in the ROM -- the generated
PNGs in `gba/gfx/` are committed, so the build never reads anything here.

`font.ttf` is Kenney Mini Square Mono, which renders with no antialiasing at
8px (6px advance, 5x5 ink). Kenney's assets are published CC0, but confirm
the licence of whatever font you ship before distributing a ROM.

Fonts are listed in `fonts.toml` -- one `[[font]]` entry per font, and a
project can have as many as it likes (a title face, a HUD face, digits, ...).
Each entry names its file, size, mode (`objects` or `tiles`) and colour
variants; the format is documented at the top of that file.

Adding a font:

```sh
python3 tools/gbafont.py probe assets-src/myfont.ttf   # which sizes are crisp?
$EDITOR assets-src/fonts.toml                          # add a [[font]] entry
make fonts                                             # sheets + gba/src/gfx/fonts.rs
```

then add the sheet to `gba/src/gfx/assets.rs` (`make fonts` lists any that
are missing) and use it through `crate::gfx::fonts::<name>`.

Sheets cut from the same font at the same size share a baseline and line
height whatever their charset, so a digits-only sheet lines up with the full
alphabet beside it.
