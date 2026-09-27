Source assets for `tools/gbagfx.py`. Not shipped in the ROM -- the generated
PNGs in `gba/gfx/` are committed, so the build never reads anything here.

`font.ttf` is Kenney Mini Square Mono, which renders with no antialiasing at
8px (6px advance, 5x5 ink). Kenney's assets are published CC0, but confirm
the licence of whatever font you ship before distributing a ROM.
