# Working on a Game Boy Advance game with `agb`

Guidance for agents (and humans) building GBA games in Rust with
[`agb`](https://github.com/agbrs/agb). Everything here was learned the hard
way on a real port; the parts that cost the most time are marked.

The GBA is a 240x160, 15-bit-colour, 16.78 MHz ARM7TDMI with no FPU, 128
sprites and a few kilobytes of video RAM. Most of what follows is a
consequence of one of those numbers.

---

## 1. Repo layout, and why

```
Cargo.toml          host workspace: members = ["core", "tools"], exclude = ["gba"]
rust-toolchain.toml pinned nightly (see section 2)
core/               ALL game logic. no_std, no allocator, no agb dependency.
gba/                the ROM. Its own workspace root.
  .cargo/config.toml  target + build-std + runner
tools/              host-side codegen and helper scripts. Never shipped.
```

**Put every rule in `core/` and keep `agb` out of it.** This is the single
highest-value decision available. `cargo test -p <core>` then runs natively in
milliseconds, and the rules — the part that must not be wrong — are tested
without an emulator in the loop. Only presentation lives in `gba/`.

```rust
#![cfg_attr(not(test), no_std)]   // no_std on device, std for the test harness
```

**`gba/` must be its own workspace root.** Its `.cargo/config.toml` sets
`target = "thumbv4t-none-eabi"` and `build-std`, and cargo config is
discovered by walking up from the current directory — so a single workspace
would force the GBA target onto host crates and break `cargo test` and any
codegen tool. Hence `exclude = ["gba"]` at the root and an empty
`[workspace]` table in `gba/Cargo.toml`.

**No allocator.** Fixed-size arrays throughout. `alloc` is available but every
allocation is a chance to fragment 256KB of EWRAM; games of this size do not
need it.

**Drive state through commands and events.** The UI sends a `Cmd` and reads
back `Event`s; it never mutates game state directly.

```rust
enum Cmd   { /* what the player asked for */ }
enum Event { /* what actually happened, including Rejected(Reason) */ }
fn apply(&mut self, cmd: Cmd) -> Events;
```

A test then becomes a script of commands with assertions on the events, and
rejected input gets a reason you can show the player instead of a dead button.

---

## 2. Toolchain

**`agb` does not build on arbitrary nightlies.** Cost us an hour. agb 0.25.0
fails on 2026-09 nightlies because the upstream `allocator_api` rework broke
`agb_hashmap`. Pin a nightly from the week the agb version was published:

```toml
# rust-toolchain.toml
[toolchain]
channel = "nightly-2026-07-22"     # agb 0.25.0 was published 2026-07-22
components = ["rust-src", "clippy", "rustfmt"]
```

Bump the pin only together with the agb version, and only after a build.

```sh
rustup toolchain install nightly-YYYY-MM-DD -c rust-src -c clippy -c rustfmt
cargo install agb-gbafix
```

**Never run two `rustup toolchain install` of the same toolchain at once** —
including one in the background and one triggered implicitly by `cargo`. It
corrupts the toolchain with `Directory not empty (os error 39)`. Recover with
`rustup toolchain uninstall` then reinstall.

`[profile.dev] opt-level = 3` is not optional: an unoptimised GBA build is too
slow to play.

---

## 3. Making a ROM

```sh
agb-gbafix target/thumbv4t-none-eabi/release/<bin> \
  --title GAMENAME --gamecode ABCD --makercode XX --padding --output game.gba
```

- **`--padding` matters.** It rounds the ROM up to a power of two. mGBA does
  not care; plenty of loaders and cores do, and a non-power-of-two ROM is a
  classic "works here, black screen on device".
- **There is no save-type flag.** Do not look for one. The SRAM/Flash marker
  string is emitted by `agb` itself once the save code is linked in; verify
  with `strings game.gba | grep -E 'SRAM_V|FLASH|EEPROM'`.

Validate a built ROM (cheap, catches real problems):

```python
rom = open("game.gba","rb").read()
chk = 0
for b in rom[0xA0:0xBD]: chk = (chk - b) & 0xFF
assert (chk - 0x19) & 0xFF == rom[0xBD]          # header checksum
assert rom[0xB2] == 0x96                          # fixed byte
assert len(rom) == 1 << (len(rom)-1).bit_length() # padded
```

---

## 4. Hardware limits worth memorising

**Sprite sizes are a fixed set.** Squares 8, 16, 32, 64; rectangles 16x8,
32x8, 32x16, 64x32, 8x16, 8x32, 16x32, 32x64. **24x24 is not legal** and the
`include_aseprite!` macro will reject it at compile time.

> If you want a 24x24 look, draw 24x24 of art centred in a 32x32 frame. It is
> visually identical, costs nothing at runtime, and needs no per-cell offset
> maths. Same trick for any "almost a legal size" request.

**Colour.** 4bpp means 15 colours plus transparent per sprite, and one
16-colour palette per background tile. 8bpp doubles VRAM and ROM for 255
colours — prefer 4bpp. Everything is 15-bit: quantise with `(c >> 3) << 3` in
your asset pipeline so previews match hardware exactly.

**A background is easiest to reason about if the whole image fits one
16-colour palette** — then no individual tile can possibly overflow.

**Tiles.** 8x8. A charblock holds 512 4bpp tiles. `deduplicate` in
`include_background_gfx!` is free and very effective: a full-screen UI with
flat fields dropped from 600 tiles to 48 in practice. Photographic art dedupes
badly — keep large art on a flat backdrop.

**Objects.** 128 in OAM, and the per-scanline limit bites before the total
does. Budget deliberately: anything static on a flat surface belongs in
background tiles, not objects (see section 5).

**No FPU.** Use `agb::fixnum`. Better still, precompute at build time: if a
value depends only on an integer (a level number, a frame index), bake the
whole table into generated Rust and do no arithmetic on device at all.

**Blending has 4 fractional bits.** `frame.blend().darken(x)` takes
`Num<u8, 4>` — seventeen steps from clear to black. Compute fades in raw
sixteenths (`Num::from_raw(n)`) rather than dividing floats.

---

## 5. Text: use two systems, and avoid agb's

`agb` has a real text renderer (`Layout`, `ObjectTextRenderer`). It is
correct, it does kerning and wrapping — and it is slow enough that laying out
a line can cost you a frame. agb's own docs tell you to spread it over
multiple frames. **For fixed game text you can avoid it entirely.**

| Use | When | Cost |
|---|---|---|
| **Background tiles** | Static text on a flat-coloured surface: HUD labels, instructions, menus over a plain panel | Zero objects |
| **Object font** | Text over uneven art, text that moves, or anywhere you want tight spacing | One object per glyph |

Rules of thumb:

- A screenful of static text is **always** tiles. Thirty characters across a
  dozen lines is several hundred glyphs and you have 128 objects.
- Tiles sit on the 8px grid. A 6px-wide font in an 8px cell looks airy; that
  is fine for a HUD and wrong for a title menu.
- Objects can sit at the font's natural advance, so menus set tight.

**Background palette index 0 is the global backdrop, not per-tile
transparency.** A text *tile* therefore carries its own background colour, so
you need one charset image per surface colour it will sit on (e.g. one for the
grey HUD panel, one for the dark menu panel, plus a dimmed variant for
unavailable entries). Object glyphs are genuinely transparent and need no
variants.

**Finding a font that rasterises crisply is the whole trick.** A pixel font
rendered at its design size produces zero antialiased pixels, which is exactly
what you want for a 15-bit indexed palette. Test before committing:

```python
im = Image.new("L", (120, 20), 0)
ImageDraw.Draw(im).text((0, 0), "0123456789", font=ImageFont.truetype(path, size), fill=255)
aa = sum(1 for p in im.getdata() if 0 < p < 255)
assert aa == 0, f"{size}px antialiases; try the font's design size"
```

Kenney Mini Square Mono at 8px gives 0 antialiased pixels, a 6px advance and
5x5 ink. Off-size (10px) it antialiases heavily — size matters more than the
font.

Numbers deserve their own path: a small digit strip placed at the font's
advance, with a second colour variant for highlighting, beats a general text
renderer for anything that updates every frame.

---

## 6. Asset pipeline

**Generate art with a script, commit the output.** The build must not depend
on Pillow, a font, or a source repo. Regeneration is an explicit `make
gen-art`, and the diff is reviewable.

**Make the generator enforce GBA limits and fail.** This is the highest-value
part of the pipeline — it turns a class of runtime mystery into a build error:

```python
def check_background(path):           # per-tile and whole-image colour count,
    ...                               # and unique tiles vs the 512 charblock
def check_sprites(path, size):        # <= 15 opaque colours per frame
```

**Quantise to 15-bit in the generator.** Then a PNG preview is exactly what
the hardware shows, and you can iterate on art without an emulator.

**Do not naively downscale high-resolution art.** Resampling a 140x140 die to
32x32 turns detail to mush. Either synthesise at the target size (sample the
source for its palette, then draw), or start from flat vector-like art.

**Watch out for SVG rasterisers.** ImageMagick's built-in renderer handles
filters, masks and gradients badly and will silently give you a brown smudge.
Check the output before building on it, or use `resvg`/`rsvg-convert`.

**Generated data tables: commit the file, do not use `build.rs`.** A build
script drags a parser into a cross-compiled `no_std` build for data that never
changes, and a committed table is greppable at 1am when a number is wrong.

---

## 7. Verification: look at actual frames

**A preview composited from your own art is not verification.** We built
pixel-accurate Python previews of every screen and they looked perfect. The
first real capture from the ROM immediately showed a number drawn on top of
another element, because the preview and the game read the coordinate from
different places. Previews catch art problems. Only the ROM catches code.

**Capture frames headlessly.** agb ships
`emulator/screenshot-generator`: it runs mGBA with no window, steps N frames
and writes a PNG.

```sh
git clone --depth 1 https://github.com/agbrs/agb && cd agb
LIBCLANG_PATH=/usr/lib64 \
BINDGEN_EXTRA_CLANG_ARGS=-resource-dir=/usr/lib/clang/22 \
CMAKE_POLICY_VERSION_MINIMUM=3.5 \
  cargo build --release -p screenshot-generator
cp target/release/screenshot-generator ~/.cargo/bin/
```

It compiles mGBA, so it needs `cmake` and `elfutils-libelf-devel`. The three
environment variables work around common Fedora packaging:

| Symptom | Cause | Fix |
|---|---|---|
| `limits.h file not found` | `clang-libs` ships no builtin headers | `BINDGEN_EXTRA_CLANG_ARGS=-resource-dir=/usr/lib/clang/<ver>` |
| `libclang` not found | no unversioned `.so` symlink without `clang-devel` | `LIBCLANG_PATH=/usr/lib64` |
| CMake refuses mGBA | CMake 4 rejects old `cmake_minimum_required` | `CMAKE_POLICY_VERSION_MINIMUM=3.5` |

**Add a `capture` cargo feature to reach screens that need input.** The
generator cannot press buttons, so gate a script that drives the game to each
screen at fixed frame numbers, then photograph those frames. Compiled out of
real builds.

```rust
#[cfg(feature = "capture")]
fn capture_script(&mut self) {
    match self.frame_counter {
        220 => self.enter(Screen::Menu),
        320 => self.start_game(),
        _ => {}
    }
}
```

**Do not fight the desktop for screenshots.** GNOME refuses
`org.gnome.Shell.Screenshot` for unsandboxed callers (`AccessDenied`), and
ImageMagick's `import` needs X11 utilities that are not installed on a Wayland
box. The emulator route is better anyway: deterministic, headless, scriptable.

**Read the panic output.** agb's panic handler prints the message and source
line to the mGBA debug log, and `tools/mgba.sh` enables it. A crashing ROM
tells you exactly where:

```
[FATAL] GBA Debug: Error: panicked at src/gfx/hudtiles.rs:120:55:
index out of bounds: the len is 45 but the index is 4294967295
```

---

## 8. Emulator and device compatibility

**`agb` requires a working BIOS.** Its entrypoint calls `swi 0x0B` (CpuSet) to
copy its EWRAM section *before any game code runs*, and `swi 0x05`
(VBlankIntrWait) every frame. Neither is in the ROM.

The consequence: a core with weak BIOS emulation does not glitch, it shows
**nothing at all** — there is never a first frame.

| Target | Result |
|---|---|
| mGBA | Works. Good high-level BIOS. |
| gpSP + official `gba_bios.bin` | Works. |
| gpSP with its built-in BIOS replacement | Black screen. Incomplete SWI coverage. |
| Real hardware / flashcart | Works. Real BIOS. |

Confirmed on a TrimUI Brick, where the **folder name picks the core**: a
`Game Boy Advance (GBA)` folder runs gpSP and black-screens; `Game Boy Advance
(MGBA)` runs mGBA and works. Expect the same shape of problem on any handheld
that defaults to a fast-but-loose core.

**Keep a control ROM.** Build the stock `agb::no_game` demo, ship it next to
your game, and when a device misbehaves test both. If the control fails too,
the device cannot run agb output and the problem is not your game. This turns
an open-ended debugging session into one decision.

**The Nintendo boot animation comes from the BIOS, not the ROM.** Do not try
to draw one: reproducing Nintendo's branding in homebrew implies a licence you
do not have, and it is unnecessary — the header logo `agb-gbafix` writes is
what the hardware checks, and emulators play the animation when given a BIOS.

---

## 9. agb API notes

Frame loop — `show()` renders, `commit()` waits for vblank and swaps:

```rust
let mut gfx = gba.graphics.get();
loop {
    update();
    let mut frame = gfx.frame();
    thing.show(&mut frame);
    mixer.frame();          // every frame once audio exists, or it skips
    frame.commit();
}
```

- `agb::println!` **does not accept a trailing comma.** It is a `$($x:expr),*`
  macro and the error ("unexpected end of macro invocation") does not say so.
- Buttons are `Button::Start`, `Button::Select` — not `START`.
- `include_aseprite!` takes a size prefix to split a strip:
  `32 "gfx/tokens.png"` makes 32x32 sub-sprites. Statics are named after the
  file, uppercased, hyphens to underscores.
- `include_background_gfx!` optimises palettes across everything in **one**
  invocation — put images that share a surface colour in the same macro call.
- `Object::new(sprite).set_pos((x, y)).show(frame)` — `SpriteVram` is
  reference counted and deduplicated, so repeated sprites cost VRAM once.
- Save: `agb::save::SaveSlotManager` owns the serde codec (postcard
  underneath). Hand it `#[derive(Serialize, Deserialize)]` structs directly.

---

## 10. Bugs we actually hit

- **Sentinel values plus a flush-everything-first-frame.** A tile shadow
  buffer seeded with `usize::MAX` to mean "never written", then flushed
  wholesale on frame one, indexed the tile table out of bounds and took the
  ROM down. Initialise shadows to a *valid* blank, and bounds-check lookups so
  a bad glyph degrades to a space rather than a crash.
- **Coordinates duplicated between a preview script and the game.** They
  drifted; the preview was right and the game drew a number over a UI element.
  Keep layout constants in one place and assert on them (`const _: () =
  assert!(...)` is free and catches band arithmetic that no longer sums to
  240 or 160).
- **Dead code written ahead of use.** A dozen "I'll need this for the shop"
  warnings make a real warning invisible. Delete it; it is a few lines to
  re-add.
- **`gba/target/` committed.** `/target` in `.gitignore` only matches the
  root. Use `target/`.

---

## 11. Makefile targets worth having

```make
test          # host unit tests -- the gate for logic changes
run           # cargo run, via a runner script that finds mGBA
release       # padded, header-fixed .gba
shots         # headless screenshots of every screen into docs/
gen-art       # regenerate committed art
```

Resolve the emulator in a script rather than hardcoding `mgba-qt` in
`.cargo/config.toml`: people install it from a package, a flatpak or an
AppImage, and `tools/mgba.sh` makes `cargo run` work for all three.
